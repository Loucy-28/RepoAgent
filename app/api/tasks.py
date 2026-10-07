import uuid
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.task_service import TaskService
from app.services.repository_service import RepositoryService
from app.services.git_workflow import git_workflow
from app.agent.state import AgentState, AgentPhase
from app.agent.graph import agent_graph
from app.db.models import Task
from app.db.enums import TaskStatus
from app.db.session import async_session_factory
from app.observability.logger import get_logger

from sqlalchemy import select

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    repository_id: str
    description: str
    max_iterations: int = Field(default=5, ge=1, le=20)


class TaskResponse(BaseModel):
    id: str
    repository_id: str
    description: str
    status: str
    current_step: str
    iteration: int
    max_iterations: int
    error_message: str
    created_at: str
    completed_at: Optional[str] = None

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int


class ReviewRequest(BaseModel):
    comment: str = ""


def _task_to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=str(task.id),
        repository_id=str(task.repository_id),
        description=task.description,
        status=task.status.value,
        current_step=task.current_step or "",
        iteration=task.iteration or 0,
        max_iterations=task.max_iterations or 5,
        error_message=task.error_message or "",
        created_at=task.created_at.isoformat() if task.created_at else "",
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


async def _run_agent(task_id: str, repo_id: str, description: str, repo_path: str, max_iterations: int):
    from app.services.redis_client import RedisLock

    repo_lock = RedisLock(f"repo:{repo_id}", ttl=max_iterations * 60)
    acquired = await repo_lock.acquire()
    if not acquired:
        logger.warning("agent_blocked_by_repo_lock", task_id=task_id, repo_id=repo_id)
        await TaskService.update_status(task_id, TaskStatus.FAILED, current_step="failed")
        return

    try:
        state = AgentState(
            task_id=task_id,
            repository_id=repo_id,
            description=description,
            max_iterations=max_iterations,
            repo_path=repo_path,
        )
        final_state = await agent_graph.run(state)

        async with async_session_factory() as session:
            result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_id)))
            task = result.scalar_one_or_none()
            if task:
                task.result = {
                    **(task.result or {}),
                    "branch_name": final_state.branch_name,
                    "diff": final_state.diff,
                    "edits": final_state.edits,
                    "test_passed": final_state.test_passed,
                }
                await session.commit()
    finally:
        await repo_lock.release()


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(req: CreateTaskRequest, background_tasks: BackgroundTasks):
    repo = await RepositoryService.get_repository(req.repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    task = await TaskService.create_task(
        repository_id=req.repository_id,
        description=req.description,
        max_iterations=req.max_iterations,
    )

    background_tasks.add_task(
        _run_agent,
        str(task.id),
        req.repository_id,
        req.description,
        repo.path,
        req.max_iterations,
    )

    logger.info("task_created_and_queued", task_id=str(task.id))
    return _task_to_response(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    task = await TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_response(task)


@router.get("", response_model=TaskListResponse)
async def list_tasks(repository_id: Optional[str] = None, limit: int = 50):
    tasks = await TaskService.list_tasks(repository_id, limit)
    return TaskListResponse(
        tasks=[_task_to_response(t) for t in tasks],
        total=len(tasks),
    )


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    success = await TaskService.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel task")
    return {"message": "Task cancelled", "task_id": task_id}


@router.get("/{task_id}/diff")
async def get_task_diff(task_id: str):
    task = await TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    branch_name = task.result.get("branch_name", "") if task.result else ""
    diff = task.result.get("diff", "") if task.result else ""
    return {
        "task_id": task_id,
        "status": task.status.value,
        "branch": branch_name,
        "diff": diff,
    }


@router.post("/{task_id}/approve")
async def approve_task(task_id: str, req: ReviewRequest = ReviewRequest()):
    task = await TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != TaskStatus.WAITING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Task is not waiting for review (current status: {task.status.value})",
        )

    async with async_session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_id)))
        task = result.scalar_one_or_none()
        if task:
            task.status = TaskStatus.APPROVED
            task.current_step = "approved"
            task.result = {**(task.result or {}), "review_comment": req.comment, "approved_at": datetime.now(timezone.utc).isoformat()}
            task.updated_at = datetime.now(timezone.utc)
            await session.commit()

    logger.info("task_approved", task_id=task_id, comment=req.comment)
    return {
        "task_id": task_id,
        "status": "APPROVED",
        "message": "Task approved. Ready for merge.",
        "comment": req.comment,
    }


@router.post("/{task_id}/reject")
async def reject_task(task_id: str, req: ReviewRequest = ReviewRequest()):
    task = await TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != TaskStatus.WAITING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Task is not waiting for review (current status: {task.status.value})",
        )

    async with async_session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_id)))
        task = result.scalar_one_or_none()
        if task:
            task.status = TaskStatus.REJECTED
            task.current_step = "rejected"
            task.error_message = req.comment or "Rejected by reviewer"
            task.completed_at = datetime.now(timezone.utc)
            task.updated_at = datetime.now(timezone.utc)
            await session.commit()

    logger.info("task_rejected", task_id=task_id, comment=req.comment)
    return {
        "task_id": task_id,
        "status": "REJECTED",
        "message": "Task rejected.",
        "comment": req.comment,
    }


@router.post("/{task_id}/merge")
async def merge_task(task_id: str):
    task = await TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != TaskStatus.APPROVED:
        raise HTTPException(
            status_code=400,
            detail=f"Task must be approved before merge (current status: {task.status.value})",
        )

    repo = await RepositoryService.get_repository(str(task.repository_id))
    merge_result = {}
    if repo and repo.path:
        branch_name = f"agent/task-{task_id}"
        if task.result and task.result.get("branch_name"):
            branch_name = task.result["branch_name"]
        merge_result = git_workflow.merge_to_main(repo.path, branch_name)
    else:
        merge_result = {"merged": False, "error": "Repository path not found"}

    if merge_result.get("merged"):
        async with async_session_factory() as session:
            result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_id)))
            task = result.scalar_one_or_none()
            if task:
                task.status = TaskStatus.MERGED
                task.current_step = "merged"
                task.completed_at = datetime.now(timezone.utc)
                task.updated_at = datetime.now(timezone.utc)
                task.result = {**(task.result or {}), "merge": merge_result}
                await session.commit()

        logger.info("task_merged", task_id=task_id, merge=merge_result)
        return {
            "task_id": task_id,
            "status": "MERGED",
            "message": "Task changes merged.",
            "merge": merge_result,
        }
    else:
        merge_error = merge_result.get("error", "Merge failed for unknown reason")
        logger.error("merge_failed_api", task_id=task_id, error=merge_error)
        raise HTTPException(
            status_code=409,
            detail=f"Merge failed: {merge_error}",
        )

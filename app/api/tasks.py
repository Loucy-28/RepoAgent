import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.task_service import TaskService
from app.services.repository_service import RepositoryService
from app.agent.state import AgentState, AgentPhase
from app.agent.graph import agent_graph
from app.db.models import Task
from app.db.enums import TaskStatus
from app.observability.logger import get_logger

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
    state = AgentState(
        task_id=task_id,
        repository_id=repo_id,
        description=description,
        max_iterations=max_iterations,
        repo_path=repo_path,
    )
    await agent_graph.run(state)


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

    diff = task.result.get("diff", "") if task.result else ""
    return {
        "task_id": task_id,
        "status": task.status.value,
        "diff": diff,
    }

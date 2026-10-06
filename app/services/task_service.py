import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Task, AgentStep, Repository
from app.db.enums import TaskStatus, StepType
from app.db.session import async_session_factory
from app.observability.logger import get_logger
from app.services.redis_client import RedisLock, AgentStateStore

logger = get_logger(__name__)


class TaskService:
    @staticmethod
    async def create_task(repository_id: str, description: str, max_iterations: int = 5) -> Task:
        async with async_session_factory() as session:
            task = Task(
                repository_id=uuid.UUID(repository_id),
                description=description,
                status=TaskStatus.CREATED,
                max_iterations=max_iterations,
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            logger.info("task_created", task_id=str(task.id), repository_id=repository_id)
            return task

    @staticmethod
    async def get_task(task_id: str) -> Optional[Task]:
        async with async_session_factory() as session:
            result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_id)))
            return result.scalar_one_or_none()

    @staticmethod
    async def update_status(task_id: str, status: TaskStatus, current_step: str = "", error: str = ""):
        async with async_session_factory() as session:
            result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_id)))
            task = result.scalar_one_or_none()
            if task:
                task.status = status
                if current_step:
                    task.current_step = current_step
                if error:
                    task.error_message = error
                if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    task.completed_at = datetime.now(timezone.utc)
                task.updated_at = datetime.now(timezone.utc)
                await session.commit()
                logger.info("task_status_updated", task_id=task_id, status=status.value)

    @staticmethod
    async def increment_iteration(task_id: str) -> int:
        async with async_session_factory() as session:
            result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_id)))
            task = result.scalar_one_or_none()
            if task:
                task.iteration = (task.iteration or 0) + 1
                await session.commit()
                return task.iteration
            return 0

    @staticmethod
    async def cancel_task(task_id: str) -> bool:
        task = await TaskService.get_task(task_id)
        if not task:
            return False
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return False
        await TaskService.update_status(task_id, TaskStatus.CANCELLED)
        lock = RedisLock(task_id)
        await lock.release()
        await AgentStateStore.delete(task_id)
        logger.info("task_cancelled", task_id=task_id)
        return True

    @staticmethod
    async def record_step(task_id: str, step_type: StepType, status: str,
                          input_data: Optional[dict] = None, output_data: Optional[dict] = None,
                          error: str = "", duration_ms: int = 0):
        async with async_session_factory() as session:
            step = AgentStep(
                task_id=uuid.UUID(task_id),
                step_type=step_type,
                status=status,
                input_data=input_data or {},
                output_data=output_data or {},
                error=error,
                duration_ms=duration_ms,
            )
            session.add(step)
            await session.commit()

    @staticmethod
    async def list_tasks(repository_id: Optional[str] = None, limit: int = 50) -> list[Task]:
        async with async_session_factory() as session:
            query = select(Task).order_by(Task.created_at.desc()).limit(limit)
            if repository_id:
                query = query.where(Task.repository_id == uuid.UUID(repository_id))
            result = await session.execute(query)
            return list(result.scalars().all())

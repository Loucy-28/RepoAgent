from typing import Optional
from app.db.enums import TaskStatus
from app.services.task_service import TaskService
from app.services.redis_client import AgentStateStore
from app.observability.logger import get_logger

logger = get_logger(__name__)


class CheckpointService:
    @staticmethod
    async def save_checkpoint(task_id: str, state: dict):
        await AgentStateStore.set(task_id, state)
        logger.info("checkpoint_saved", task_id=task_id, step=state.get("step", ""))

    @staticmethod
    async def load_checkpoint(task_id: str) -> Optional[dict]:
        state = await AgentStateStore.get(task_id)
        if state:
            logger.info("checkpoint_loaded", task_id=task_id, step=state.get("step", ""))
        return state

    @staticmethod
    async def clear_checkpoint(task_id: str):
        await AgentStateStore.delete(task_id)
        logger.info("checkpoint_cleared", task_id=task_id)

    @staticmethod
    async def recover_task(task_id: str) -> bool:
        checkpoint = await CheckpointService.load_checkpoint(task_id)
        if not checkpoint:
            return False
        step = checkpoint.get("step", "")
        status_map = {
            "planning": TaskStatus.PLANNING,
            "searching": TaskStatus.SEARCHING,
            "analyzing": TaskStatus.ANALYZING,
            "editing": TaskStatus.EDITING,
            "testing": TaskStatus.TESTING,
            "repairing": TaskStatus.REPAIRING,
        }
        status = status_map.get(step, TaskStatus.CREATED)
        await TaskService.update_status(task_id, status, current_step=step)
        logger.info("task_recovered", task_id=task_id, status=status.value)
        return True

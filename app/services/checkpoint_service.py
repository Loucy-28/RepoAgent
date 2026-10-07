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
        phase = state.get("phase", "")
        logger.info("checkpoint_saved", task_id=task_id, phase=phase)

    @staticmethod
    async def load_checkpoint(task_id: str) -> Optional[dict]:
        state = await AgentStateStore.get(task_id)
        if state:
            phase = state.get("phase", "")
            logger.info("checkpoint_loaded", task_id=task_id, phase=phase)
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

        phase = checkpoint.get("phase", "")
        status_map = {
            "PLANNING": TaskStatus.PLANNING,
            "SEARCHING": TaskStatus.SEARCHING,
            "ANALYZING": TaskStatus.ANALYZING,
            "EDITING": TaskStatus.EDITING,
            "TESTING": TaskStatus.TESTING,
            "REPAIRING": TaskStatus.REPAIRING,
            "REPLANNING": TaskStatus.REPLANNING,
            "WAITING_REVIEW": TaskStatus.WAITING_REVIEW,
        }
        status = status_map.get(phase, TaskStatus.CREATED)
        await TaskService.update_status(task_id, status, current_step=phase.lower())
        logger.info("task_recovered", task_id=task_id, status=status.value, phase=phase)
        return True

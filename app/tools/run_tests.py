from app.sandbox.manager import sandbox_manager, ExecutionResult
from app.observability.logger import get_logger

logger = get_logger(__name__)


def run_tests(code: str, language: str = "python") -> dict:
    result = sandbox_manager.execute_with_timeout(code, language)
    return {
        "success": result.success,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "duration_ms": result.duration_ms,
    }

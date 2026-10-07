from enum import Enum
from typing import Optional
from app.observability.logger import get_logger

logger = get_logger(__name__)


class ToolName(str, Enum):
    SEARCH_CODE = "search_code"
    READ_FILE = "read_file"
    LIST_FILES = "list_files"
    GET_DEPENDENCIES = "get_dependencies"
    EDIT_FILE = "edit_file"
    GIT_DIFF = "git_diff"
    RUN_TESTS = "run_tests"
    CREATE_PLAN = "create_plan"
    REVIEW_CODE = "review_code"
    REPLAN = "replan"


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    SEARCH = "search"
    REVIEW = "review"
    REFACTOR = "refactor"
    VALIDATOR = "validator"


TOOL_PERMISSIONS: dict[AgentRole, set[ToolName]] = {
    AgentRole.ORCHESTRATOR: {
        ToolName.CREATE_PLAN,
        ToolName.REPLAN,
    },
    AgentRole.SEARCH: {
        ToolName.SEARCH_CODE,
        ToolName.READ_FILE,
        ToolName.LIST_FILES,
        ToolName.GET_DEPENDENCIES,
    },
    AgentRole.REVIEW: {
        ToolName.SEARCH_CODE,
        ToolName.READ_FILE,
        ToolName.GET_DEPENDENCIES,
        ToolName.REVIEW_CODE,
    },
    AgentRole.REFACTOR: {
        ToolName.READ_FILE,
        ToolName.EDIT_FILE,
        ToolName.GIT_DIFF,
    },
    AgentRole.VALIDATOR: {
        ToolName.RUN_TESTS,
        ToolName.READ_FILE,
    },
}


class ToolPermissionChecker:
    def check(self, role: AgentRole, tool: ToolName) -> bool:
        allowed = TOOL_PERMISSIONS.get(role, set())
        permitted = tool in allowed
        if not permitted:
            logger.warning(
                "tool_permission_denied",
                role=role.value,
                tool=tool.value,
                allowed=[t.value for t in allowed],
            )
        return permitted

    def get_allowed_tools(self, role: AgentRole) -> list[str]:
        return [t.value for t in TOOL_PERMISSIONS.get(role, set())]


permission_checker = ToolPermissionChecker()

import time
from typing import Any

from app.agent.permissions import AgentRole, ToolName, permission_checker
from app.observability.logger import get_logger

logger = get_logger(__name__)


class ToolExecutionError(Exception):
    pass


class ToolExecutor:
    def __init__(self):
        self._registry: dict[str, callable] = {}
        self._execution_log: list[dict] = []

    def register(self, tool_name: str, handler: callable):
        self._registry[tool_name] = handler
        logger.info("tool_registered", tool=tool_name)

    async def execute(
        self,
        role: AgentRole,
        tool_name: ToolName,
        args: dict[str, Any] = None,
    ) -> dict:
        if not permission_checker.check(role, tool_name):
            logger.warning(
                "tool_permission_denied",
                role=role.value,
                tool=tool_name.value,
            )
            return {"error": "permission denied", "tool": tool_name.value, "role": role.value}

        handler = self._registry.get(tool_name.value)
        if not handler:
            logger.error("tool_not_registered", tool=tool_name.value)
            return {"error": f"tool not registered: {tool_name.value}"}

        start = time.time()
        try:
            result = await handler(**(args or {}))
            duration_ms = int((time.time() - start) * 1000)

            record = {
                "role": role.value,
                "tool": tool_name.value,
                "success": not result.get("error"),
                "duration_ms": duration_ms,
            }
            self._execution_log.append(record)

            logger.info(
                "tool_executed",
                role=role.value,
                tool=tool_name.value,
                success=record["success"],
                duration_ms=duration_ms,
            )
            return result

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error("tool_execution_error", tool=tool_name.value, error=str(e))
            self._execution_log.append({
                "role": role.value,
                "tool": tool_name.value,
                "success": False,
                "error": str(e),
                "duration_ms": duration_ms,
            })
            return {"error": str(e), "tool": tool_name.value}

    def get_execution_log(self) -> list[dict]:
        return list(self._execution_log)

    def clear_log(self):
        self._execution_log.clear()


tool_executor = ToolExecutor()


def _register_default_tools():
    async def _search_code(query: str, repository_id: str = "", repo_path: str = "", limit: int = 10, **_):
        from app.code.search import code_search
        results = await code_search.hybrid_search(repository_id or "default", query, limit=limit)
        return {
            "results": [
                {
                    "file_path": r.file_path,
                    "function_name": r.function_name,
                    "class_name": r.class_name,
                    "code": r.code[:500],
                    "score": r.score,
                }
                for r in results
            ],
            "total": len(results),
        }

    async def _read_file(file_path: str, start_line: int = None, end_line: int = None, **_):
        from app.tools.read_file import read_file
        return read_file(file_path, start_line, end_line)

    async def _list_files(repo_path: str, **_):
        from app.services.repository_service import RepositoryService
        files = RepositoryService.scan_files(repo_path)
        return {"files": files, "total": len(files)}

    async def _get_dependencies(file_path: str, **_):
        from app.code.dependency_graph import dependency_graph
        return dependency_graph.get_dependencies(file_path)

    async def _edit_file(file_path: str, new_content: str, start_line: int = None, end_line: int = None, allowed_root: str = "", **_):
        from app.tools.edit_file import edit_file
        return edit_file(file_path, new_content, start_line, end_line, allowed_root=allowed_root)

    async def _git_diff(repo_path: str, branch_name: str, **_):
        from app.services.git_workflow import git_workflow
        return git_workflow.generate_diff(repo_path, branch_name)

    async def _run_tests(test_code: str, language: str = "python", repo_path: str = "", **_):
        from app.sandbox.manager import sandbox_manager, SandboxUnavailableError
        try:
            result = sandbox_manager.execute_with_timeout(test_code, language, repo_path=repo_path)
            return {
                "success": result.success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "duration_ms": result.duration_ms,
            }
        except SandboxUnavailableError as e:
            return {"error": str(e), "success": False, "sandbox_error": True}

    async def _create_plan(description: str, repo_context: str = "", **_):
        from app.agent.planner import Planner
        planner = Planner()
        plan = await planner.create_plan(description, repo_context)
        return {"plan": plan}

    async def _review_code(code: str, file_path: str, language: str = "python", **_):
        from app.agent.planner import Planner
        planner = Planner()
        review = await planner.review_code(code, file_path, language)
        return {"review": review}

    async def _replan(description: str, current_plan: str, failure_summary: str, **_):
        from app.agent.planner import Planner
        planner = Planner()
        new_plan = await planner.replan(description, current_plan, failure_summary)
        return {"plan": new_plan}

    tool_executor.register(ToolName.SEARCH_CODE.value, _search_code)
    tool_executor.register(ToolName.READ_FILE.value, _read_file)
    tool_executor.register(ToolName.LIST_FILES.value, _list_files)
    tool_executor.register(ToolName.GET_DEPENDENCIES.value, _get_dependencies)
    tool_executor.register(ToolName.EDIT_FILE.value, _edit_file)
    tool_executor.register(ToolName.GIT_DIFF.value, _git_diff)
    tool_executor.register(ToolName.RUN_TESTS.value, _run_tests)
    tool_executor.register(ToolName.CREATE_PLAN.value, _create_plan)
    tool_executor.register(ToolName.REVIEW_CODE.value, _review_code)
    tool_executor.register(ToolName.REPLAN.value, _replan)

    logger.info("default_tools_registered", count=len(tool_executor._registry))


_register_default_tools()

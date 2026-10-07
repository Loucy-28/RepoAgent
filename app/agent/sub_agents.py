from typing import Optional
from app.agent.permissions import AgentRole, ToolName, permission_checker
from app.agent.tool_executor import tool_executor
from app.agent.planner import Planner
from app.code.search import code_search
from app.code.dependency_graph import dependency_graph
from app.observability.logger import get_logger

logger = get_logger(__name__)


class SearchAgent:
    role = AgentRole.SEARCH

    def __init__(self):
        self._planner = None

    @property
    def planner(self):
        if self._planner is None:
            self._planner = Planner()
        return self._planner

    async def search(self, repository_id: str, query: str, repo_path: str = "", limit: int = 10) -> dict:
        search_result = await tool_executor.execute(
            self.role, ToolName.SEARCH_CODE,
            {"query": query, "repository_id": repository_id, "limit": limit},
        )
        if "error" in search_result:
            return search_result

        search_data = search_result

        if repo_path:
            dep_data = []
            for r in search_data.get("results", [])[:5]:
                import os
                file_path = r.get("file_path", "")
                full_path = os.path.join(repo_path, file_path) if not os.path.isabs(file_path) else file_path
                dep_info = dependency_graph.get_dependencies(full_path)
                if "error" not in dep_info:
                    dep_data.append({
                        "file_path": file_path,
                        "imported_by": dep_info.get("imported_by", []),
                        "calls": dep_info.get("calls", []),
                    })
            search_data["dependencies"] = dep_data

        logger.info("search_agent_complete", results=search_data.get("total", 0))
        return search_data


class ReviewAgent:
    role = AgentRole.REVIEW

    def __init__(self):
        self._planner = None

    @property
    def planner(self):
        if self._planner is None:
            self._planner = Planner()
        return self._planner

    async def review(self, code: str, file_path: str, language: str = "python", dep_context: str = "") -> dict:
        if not permission_checker.check(self.role, ToolName.REVIEW_CODE):
            return {"error": "permission denied"}

        review_result = await tool_executor.execute(
            self.role, ToolName.REVIEW_CODE,
            {"code": code, "file_path": file_path, "language": language},
        )
        if "error" in review_result:
            return review_result

        review_text = review_result.get("review", "")

        if dep_context:
            review_text += f"\n\nDependency context:\n{dep_context}"

        findings = self._parse_findings(review_text)

        logger.info("review_agent_complete", file=file_path, findings=len(findings))
        return {
            "file_path": file_path,
            "review": review_text,
            "findings": findings,
        }

    def _parse_findings(self, review_text: str) -> list[dict]:
        findings = []
        current = {}
        for line in review_text.splitlines():
            line = line.strip()
            if line.startswith("- Type:") or line.startswith("Type:"):
                if current:
                    findings.append(current)
                current = {"type": line.split(":", 1)[1].strip() if ":" in line else ""}
            elif line.startswith("- Severity:") or line.startswith("Severity:"):
                current["severity"] = line.split(":", 1)[1].strip() if ":" in line else ""
            elif line.startswith("- Description:") or line.startswith("Description:"):
                current["description"] = line.split(":", 1)[1].strip() if ":" in line else ""
            elif line.startswith("- Suggestion:") or line.startswith("Suggestion:"):
                current["suggestion"] = line.split(":", 1)[1].strip() if ":" in line else ""
        if current:
            findings.append(current)
        return findings


class RefactorAgent:
    role = AgentRole.REFACTOR

    def __init__(self):
        self._planner = None

    @property
    def planner(self):
        if self._planner is None:
            self._planner = Planner()
        return self._planner

    async def refactor(self, code: str, file_path: str, findings: str, language: str = "python") -> dict:
        if not permission_checker.check(self.role, ToolName.EDIT_FILE):
            return {"error": "permission denied"}

        edited_code = await self.planner.generate_edit(code, file_path, findings, language)

        logger.info("refactor_agent_complete", file=file_path)
        return {
            "file_path": file_path,
            "original_code": code,
            "edited_code": edited_code,
        }


class ValidatorAgent:
    role = AgentRole.VALIDATOR

    async def validate(self, test_code: str, language: str = "python", repo_path: str = "") -> dict:
        result = await tool_executor.execute(
            self.role, ToolName.RUN_TESTS,
            {"test_code": test_code, "language": language, "repo_path": repo_path},
        )
        return result


search_agent = SearchAgent()
review_agent = ReviewAgent()
refactor_agent = RefactorAgent()
validator_agent = ValidatorAgent()

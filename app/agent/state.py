from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class AgentPhase(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    SEARCHING = "SEARCHING"
    ANALYZING = "ANALYZING"
    EDITING = "EDITING"
    TESTING = "TESTING"
    REPAIRING = "REPAIRING"
    REPLANNING = "REPLANNING"
    WAITING_REVIEW = "WAITING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MERGED = "MERGED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class ToolCallRecord:
    tool_name: str
    phase: str
    success: bool
    error: str = ""


@dataclass
class AgentState:
    task_id: str
    repository_id: str
    description: str
    phase: AgentPhase = AgentPhase.CREATED
    iteration: int = 0
    max_iterations: int = 5

    plan: str = ""
    search_results: list[dict] = field(default_factory=list)
    review_findings: list[dict] = field(default_factory=list)

    edits: list[dict] = field(default_factory=list)
    diff: str = ""

    test_result: Optional[dict] = None
    test_passed: bool = False

    error: str = ""
    messages: list[dict] = field(default_factory=list)

    repo_path: str = ""

    tool_history: list[dict] = field(default_factory=list)
    error_history: list[dict] = field(default_factory=list)
    replan_count: int = 0
    max_replans: int = 2
    loop_detected: bool = False
    branch_name: str = ""
    agent_routing: dict = field(default_factory=lambda: {"search": True, "analyze": True, "test": True})

    def record_tool_call(self, tool_name: str, phase: str, success: bool, error: str = ""):
        self.tool_history.append({
            "tool": tool_name,
            "phase": phase,
            "success": success,
            "error": error,
            "iteration": self.iteration,
        })
        if not success and error:
            self.error_history.append({
                "error": error,
                "phase": phase,
                "iteration": self.iteration,
            })

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "repository_id": self.repository_id,
            "description": self.description,
            "phase": self.phase.value,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "plan": self.plan,
            "search_results": self.search_results,
            "review_findings": self.review_findings,
            "edits": self.edits,
            "diff": self.diff,
            "test_result": self.test_result,
            "test_passed": self.test_passed,
            "error": self.error,
            "repo_path": self.repo_path,
            "tool_history": self.tool_history,
            "error_history": self.error_history,
            "replan_count": self.replan_count,
            "max_replans": self.max_replans,
            "loop_detected": self.loop_detected,
            "branch_name": self.branch_name,
            "agent_routing": self.agent_routing,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentState":
        state = cls(
            task_id=data.get("task_id", ""),
            repository_id=data.get("repository_id", ""),
            description=data.get("description", ""),
            phase=AgentPhase(data.get("phase", "CREATED")),
            iteration=data.get("iteration", 0),
            max_iterations=data.get("max_iterations", 5),
            plan=data.get("plan", ""),
            search_results=data.get("search_results", []),
            review_findings=data.get("review_findings", []),
            edits=data.get("edits", []),
            diff=data.get("diff", ""),
            test_result=data.get("test_result"),
            test_passed=data.get("test_passed", False),
            error=data.get("error", ""),
            repo_path=data.get("repo_path", ""),
            tool_history=data.get("tool_history", []),
            error_history=data.get("error_history", []),
            replan_count=data.get("replan_count", 0),
            max_replans=data.get("max_replans", 2),
            loop_detected=data.get("loop_detected", False),
            branch_name=data.get("branch_name", ""),
            agent_routing=data.get("agent_routing", {"search": True, "analyze": True, "test": True}),
        )
        return state

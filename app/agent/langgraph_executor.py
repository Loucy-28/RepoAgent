import operator
from typing import Annotated, Any, Optional

from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict

from app.observability.logger import get_logger

logger = get_logger(__name__)


class AgentGraphState(TypedDict):
    task_id: str
    repository_id: str
    description: str
    phase: str
    iteration: int
    max_iterations: int
    plan: str
    search_results: list[dict]
    review_findings: list[dict]
    edits: list[dict]
    diff: str
    test_result: Optional[dict]
    test_passed: bool
    error: str
    repo_path: str
    tool_history: list[dict]
    error_history: list[dict]
    replan_count: int
    max_replans: int
    loop_detected: bool
    branch_name: str
    agent_routing: dict


def _route_after_phase(state: AgentGraphState) -> str:
    phase = state.get("phase", "")
    routing = {
        "CREATED": "plan",
        "PLANNING": "plan",
        "SEARCHING": "search",
        "ANALYZING": "analyze",
        "EDITING": "edit",
        "TESTING": "test",
        "REPAIRING": "repair",
        "REPLANNING": "replan",
    }
    target = routing.get(phase)
    if target:
        return target
    return "end"


def _route_after_plan(state: AgentGraphState) -> str:
    phase = state.get("phase", "")
    if phase in ("COMPLETED", "FAILED", "WAITING_REVIEW"):
        return "end"
    return "search"


def _route_after_search(state: AgentGraphState) -> str:
    phase = state.get("phase", "")
    if phase in ("COMPLETED", "FAILED", "WAITING_REVIEW"):
        return "end"
    return "analyze"


def _route_after_analyze(state: AgentGraphState) -> str:
    phase = state.get("phase", "")
    if phase in ("COMPLETED", "FAILED", "WAITING_REVIEW"):
        return "end"
    return "edit"


def _route_after_edit(state: AgentGraphState) -> str:
    phase = state.get("phase", "")
    if phase in ("COMPLETED", "FAILED", "WAITING_REVIEW"):
        return "end"
    return "test"


def _route_after_test(state: AgentGraphState) -> str:
    phase = state.get("phase", "")
    if phase == "COMPLETED":
        return "end"
    if phase == "FAILED":
        return "end"
    if phase == "REPAIRING":
        return "repair"
    return "end"


def _route_after_repair(state: AgentGraphState) -> str:
    phase = state.get("phase", "")
    if phase in ("COMPLETED", "FAILED", "WAITING_REVIEW"):
        return "end"
    return "test"


def _route_after_replan(state: AgentGraphState) -> str:
    phase = state.get("phase", "")
    if phase in ("COMPLETED", "FAILED", "WAITING_REVIEW"):
        return "end"
    return "search"


def _check_iteration(state: AgentGraphState) -> str:
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 5)
    if iteration >= max_iterations:
        return "end"
    return "continue"


def build_agent_graph(handler_registry: dict) -> Any:
    graph = StateGraph(AgentGraphState)

    graph.add_node("plan", handler_registry["plan"])
    graph.add_node("search", handler_registry["search"])
    graph.add_node("analyze", handler_registry["analyze"])
    graph.add_node("edit", handler_registry["edit"])
    graph.add_node("test", handler_registry["test"])
    graph.add_node("repair", handler_registry["repair"])
    graph.add_node("replan", handler_registry["replan"])

    graph.add_edge(START, "plan")

    graph.add_conditional_edges("plan", _route_after_plan, {
        "search": "search", "end": END,
    })
    graph.add_conditional_edges("search", _route_after_search, {
        "analyze": "analyze", "end": END,
    })
    graph.add_conditional_edges("analyze", _route_after_analyze, {
        "edit": "edit", "end": END,
    })
    graph.add_conditional_edges("edit", _route_after_edit, {
        "test": "test", "end": END,
    })
    graph.add_conditional_edges("test", _route_after_test, {
        "repair": "repair", "end": END,
    })
    graph.add_conditional_edges("repair", _route_after_repair, {
        "test": "test", "end": END,
    })
    graph.add_conditional_edges("replan", _route_after_replan, {
        "search": "search", "end": END,
    })

    return graph.compile()

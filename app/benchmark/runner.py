import time
import subprocess
from typing import Optional

from app.benchmark.cases import BENCHMARK_CASES, BenchmarkCase, get_benchmark_case
from app.benchmark.metrics import BenchmarkResult, MetricsCollector, metrics_collector
from app.agent.state import AgentState
from app.agent.graph import agent_graph
from app.observability.logger import get_logger

logger = get_logger(__name__)


class BenchmarkRunner:
    def __init__(self, collector: Optional[MetricsCollector] = None):
        self.collector = collector or metrics_collector

    async def run_case(
        self,
        case: BenchmarkCase,
        repo_path: str,
        repository_id: str,
    ) -> BenchmarkResult:
        logger.info("benchmark_start", case_id=case.id, case_name=case.name)
        start = time.time()

        state = AgentState(
            task_id=f"bench-{case.id}",
            repository_id=repository_id,
            description=case.description,
            max_iterations=10,
            repo_path=repo_path,
        )

        try:
            final_state = await agent_graph.run(state)
            duration_ms = int((time.time() - start) * 1000)

            phases_visited = self._extract_phases(final_state)
            tools_used = list(set(t.get("tool", "") for t in final_state.tool_history))

            success = self._evaluate_success(case, final_state, phases_visited, tools_used)

            result = BenchmarkResult(
                case_id=case.id,
                case_name=case.name,
                category=case.category,
                difficulty=case.difficulty,
                success=success,
                duration_ms=duration_ms,
                iterations=final_state.iteration,
                phases_visited=phases_visited,
                tools_used=tools_used,
                loop_detected=final_state.loop_detected,
                replan_count=final_state.replan_count,
                test_passed=final_state.test_passed,
                edits_count=len(final_state.edits),
                error=final_state.error,
            )

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error("benchmark_error", case_id=case.id, error=str(e))
            result = BenchmarkResult(
                case_id=case.id,
                case_name=case.name,
                category=case.category,
                difficulty=case.difficulty,
                success=False,
                duration_ms=duration_ms,
                error=str(e),
            )

        self.collector.record(result)
        logger.info("benchmark_complete", case_id=case.id, success=result.success, duration_ms=result.duration_ms)
        return result

    async def run_all(
        self,
        repo_path: str,
        repository_id: str,
        categories: Optional[list[str]] = None,
    ) -> list[BenchmarkResult]:
        cases = BENCHMARK_CASES
        if categories:
            cases = [c for c in cases if c.category in categories]

        results = []
        for i, case in enumerate(cases):
            result = await self.run_case(case, repo_path, repository_id)
            results.append(result)

            if i < len(cases) - 1:
                self._reset_repo(repo_path)

        logger.info(
            "benchmark_suite_complete",
            total=len(results),
            success=sum(1 for r in results if r.success),
        )
        return results

    def _evaluate_success(
        self,
        case: BenchmarkCase,
        state: AgentState,
        phases_visited: list[str],
        tools_used: list[str],
    ) -> bool:
        if state.phase.value not in ("COMPLETED", "WAITING_REVIEW"):
            return False
        if len(state.edits) == 0:
            return False

        if case.expected_phases:
            missing_phases = [p for p in case.expected_phases if p not in phases_visited]
            if len(missing_phases) > len(case.expected_phases) // 2:
                return False

        if case.expected_tools:
            missing_tools = [t for t in case.expected_tools if t not in tools_used]
            if len(missing_tools) > len(case.expected_tools) // 2:
                return False

        return True

    def _reset_repo(self, repo_path: str):
        try:
            subprocess.run(
                ["git", "checkout", "."],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            logger.info("benchmark_repo_reset", repo=repo_path)
        except Exception as e:
            logger.warning("benchmark_repo_reset_failed", repo=repo_path, error=str(e))

    def _extract_phases(self, state: AgentState) -> list[str]:
        phases = []
        seen = set()
        for record in state.tool_history:
            phase = record.get("phase", "")
            if phase and phase not in seen:
                phases.append(phase)
                seen.add(phase)
        return phases


benchmark_runner = BenchmarkRunner()

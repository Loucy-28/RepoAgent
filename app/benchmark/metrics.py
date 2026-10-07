import time
from dataclasses import dataclass, field
from typing import Optional

from app.observability.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BenchmarkResult:
    case_id: str
    case_name: str
    category: str
    difficulty: str
    success: bool
    duration_ms: int = 0
    iterations: int = 0
    phases_visited: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    loop_detected: bool = False
    replan_count: int = 0
    test_passed: bool = False
    edits_count: int = 0
    error: str = ""


@dataclass
class MetricsSummary:
    total_runs: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_duration_ms: float = 0.0
    avg_iterations: float = 0.0
    avg_replan_count: float = 0.0
    loop_detection_rate: float = 0.0
    test_pass_rate: float = 0.0
    by_category: dict = field(default_factory=dict)
    by_difficulty: dict = field(default_factory=dict)


class MetricsCollector:
    def __init__(self):
        self._results: list[BenchmarkResult] = []

    def record(self, result: BenchmarkResult):
        self._results.append(result)
        logger.info(
            "benchmark_record",
            case_id=result.case_id,
            success=result.success,
            duration_ms=result.duration_ms,
            iterations=result.iterations,
        )

    def get_results(self) -> list[BenchmarkResult]:
        return list(self._results)

    def get_summary(self) -> MetricsSummary:
        if not self._results:
            return MetricsSummary()

        total = len(self._results)
        successes = [r for r in self._results if r.success]
        failures = [r for r in self._results if not r.success]

        summary = MetricsSummary(
            total_runs=total,
            success_count=len(successes),
            failure_count=len(failures),
            avg_duration_ms=sum(r.duration_ms for r in self._results) / total,
            avg_iterations=sum(r.iterations for r in self._results) / total,
            avg_replan_count=sum(r.replan_count for r in self._results) / total,
            loop_detection_rate=sum(1 for r in self._results if r.loop_detected) / total,
            test_pass_rate=sum(1 for r in self._results if r.test_passed) / total,
        )

        summary.by_category = self._group_by("category")
        summary.by_difficulty = self._group_by("difficulty")

        return summary

    def _group_by(self, attr: str) -> dict:
        groups: dict[str, dict] = {}
        for r in self._results:
            key = getattr(r, attr, "unknown")
            if key not in groups:
                groups[key] = {"total": 0, "success": 0, "total_duration_ms": 0}
            groups[key]["total"] += 1
            if r.success:
                groups[key]["success"] += 1
            groups[key]["total_duration_ms"] += r.duration_ms

        for key, data in groups.items():
            data["success_rate"] = data["success"] / data["total"] if data["total"] else 0
            data["avg_duration_ms"] = data["total_duration_ms"] / data["total"] if data["total"] else 0

        return groups

    def clear(self):
        self._results.clear()


metrics_collector = MetricsCollector()

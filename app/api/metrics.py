from typing import Optional

from fastapi import APIRouter, HTTPException

from app.benchmark.cases import BENCHMARK_CASES, get_benchmark_case, get_all_categories
from app.benchmark.metrics import metrics_collector
from app.benchmark.runner import benchmark_runner
from app.observability.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


@router.get("")
async def get_metrics():
    summary = metrics_collector.get_summary()
    return {
        "total_runs": summary.total_runs,
        "success_count": summary.success_count,
        "failure_count": summary.failure_count,
        "success_rate": summary.success_count / summary.total_runs if summary.total_runs else 0,
        "avg_duration_ms": round(summary.avg_duration_ms, 2),
        "avg_iterations": round(summary.avg_iterations, 2),
        "avg_replan_count": round(summary.avg_replan_count, 2),
        "loop_detection_rate": round(summary.loop_detection_rate, 4),
        "test_pass_rate": round(summary.test_pass_rate, 4),
        "by_category": summary.by_category,
        "by_difficulty": summary.by_difficulty,
    }


@router.get("/results")
async def get_results(limit: int = 50):
    results = metrics_collector.get_results()[-limit:]
    return {
        "results": [
            {
                "case_id": r.case_id,
                "case_name": r.case_name,
                "category": r.category,
                "difficulty": r.difficulty,
                "success": r.success,
                "duration_ms": r.duration_ms,
                "iterations": r.iterations,
                "phases_visited": r.phases_visited,
                "tools_used": r.tools_used,
                "loop_detected": r.loop_detected,
                "replan_count": r.replan_count,
                "test_passed": r.test_passed,
                "edits_count": r.edits_count,
                "error": r.error,
            }
            for r in results
        ],
        "total": len(results),
    }


@router.get("/benchmark-cases")
async def list_benchmark_cases(category: Optional[str] = None):
    cases = BENCHMARK_CASES
    if category:
        cases = [c for c in cases if c.category == category]
    return {
        "cases": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "category": c.category,
                "difficulty": c.difficulty,
                "success_criteria": c.success_criteria,
            }
            for c in cases
        ],
        "total": len(cases),
    }


@router.get("/categories")
async def list_categories():
    return {"categories": get_all_categories()}


@router.post("/benchmark/run/{case_id}")
async def run_benchmark(case_id: str, repo_path: str = "", repository_id: str = ""):
    case = get_benchmark_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Benchmark case {case_id} not found")

    if not repo_path:
        raise HTTPException(status_code=400, detail="repo_path query parameter is required")

    result = await benchmark_runner.run_case(case, repo_path, repository_id)
    return {
        "case_id": result.case_id,
        "case_name": result.case_name,
        "success": result.success,
        "duration_ms": result.duration_ms,
        "iterations": result.iterations,
        "loop_detected": result.loop_detected,
        "replan_count": result.replan_count,
        "test_passed": result.test_passed,
        "edits_count": result.edits_count,
        "error": result.error,
    }


@router.post("/benchmark/run-all")
async def run_all_benchmarks(repo_path: str = "", repository_id: str = "", categories: Optional[str] = None):
    if not repo_path:
        raise HTTPException(status_code=400, detail="repo_path query parameter is required")

    cat_list = categories.split(",") if categories else None
    results = await benchmark_runner.run_all(repo_path, repository_id, categories=cat_list)
    return {
        "total": len(results),
        "success": sum(1 for r in results if r.success),
        "results": [
            {
                "case_id": r.case_id,
                "case_name": r.case_name,
                "success": r.success,
                "duration_ms": r.duration_ms,
                "iterations": r.iterations,
            }
            for r in results
        ],
    }


@router.delete("/results")
async def clear_results():
    metrics_collector.clear()
    return {"message": "Metrics results cleared"}

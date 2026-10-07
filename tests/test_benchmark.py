import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.benchmark.cases import BENCHMARK_CASES, get_benchmark_case, get_all_categories, get_benchmark_cases_by_category
from app.benchmark.metrics import BenchmarkResult, MetricsCollector


def test_benchmark_cases_count():
    assert len(BENCHMARK_CASES) == 10


def test_benchmark_cases_have_unique_ids():
    ids = [c.id for c in BENCHMARK_CASES]
    assert len(ids) == len(set(ids))


def test_get_benchmark_case():
    case = get_benchmark_case("bench-001")
    assert case is not None
    assert case.name == "fix_off_by_one"
    assert case.category == "bug_fix"


def test_get_benchmark_case_not_found():
    assert get_benchmark_case("nonexistent") is None


def test_get_all_categories():
    categories = get_all_categories()
    assert "bug_fix" in categories
    assert "refactor" in categories
    assert "security" in categories


def test_get_cases_by_category():
    refactors = get_benchmark_cases_by_category("refactor")
    assert len(refactors) >= 2
    assert all(c.category == "refactor" for c in refactors)


def test_metrics_collector_empty():
    collector = MetricsCollector()
    summary = collector.get_summary()
    assert summary.total_runs == 0


def test_metrics_collector_record_and_summarize():
    collector = MetricsCollector()

    collector.record(BenchmarkResult(
        case_id="bench-001", case_name="test1", category="bug_fix",
        difficulty="easy", success=True, duration_ms=1000, iterations=3,
    ))
    collector.record(BenchmarkResult(
        case_id="bench-002", case_name="test2", category="refactor",
        difficulty="medium", success=False, duration_ms=2000, iterations=5,
        error="max iterations",
    ))

    summary = collector.get_summary()
    assert summary.total_runs == 2
    assert summary.success_count == 1
    assert summary.failure_count == 1
    assert summary.avg_duration_ms == 1500.0
    assert summary.avg_iterations == 4.0
    assert "bug_fix" in summary.by_category
    assert "refactor" in summary.by_category


def test_metrics_collector_clear():
    collector = MetricsCollector()
    collector.record(BenchmarkResult(
        case_id="bench-001", case_name="test1", category="bug_fix",
        difficulty="easy", success=True, duration_ms=500, iterations=2,
    ))
    assert len(collector.get_results()) == 1
    collector.clear()
    assert len(collector.get_results()) == 0


@pytest.mark.asyncio
async def test_metrics_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "total_runs" in data
    assert "success_rate" in data


@pytest.mark.asyncio
async def test_benchmark_cases_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/metrics/benchmark-cases")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 10
    assert len(data["cases"]) == 10


@pytest.mark.asyncio
async def test_categories_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/metrics/categories")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["categories"], list)
    assert len(data["categories"]) > 0

import os
import tempfile
import pytest

from app.code.dependency_graph import DependencyGraph


@pytest.fixture
def sample_repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "pkg"), exist_ok=True)

        with open(os.path.join(tmpdir, "pkg", "__init__.py"), "w") as f:
            f.write("")

        with open(os.path.join(tmpdir, "pkg", "utils.py"), "w") as f:
            f.write(
                "def helper():\n"
                "    return 42\n"
                "\n"
                "def format_data(x):\n"
                "    return str(x)\n"
            )

        with open(os.path.join(tmpdir, "pkg", "service.py"), "w") as f:
            f.write(
                "from pkg.utils import helper\n"
                "\n"
                "def process():\n"
                "    val = helper()\n"
                "    return format_data(val)\n"
                "\n"
                "def format_data(x):\n"
                "    return f'formatted: {x}'\n"
            )

        with open(os.path.join(tmpdir, "pkg", "controller.py"), "w") as f:
            f.write(
                "from pkg.service import process\n"
                "\n"
                "def handle():\n"
                "    result = process()\n"
                "    return result\n"
            )

        yield tmpdir


def test_build_graph(sample_repo):
    graph = DependencyGraph()
    count = graph.build(sample_repo)
    assert count >= 3


def test_import_resolution(sample_repo):
    graph = DependencyGraph()
    graph.build(sample_repo)

    service_path = os.path.join("pkg", "service.py")
    dep = graph.get_dependencies(service_path)
    assert "pkg.utils" in dep["imports"]


def test_imported_by_resolution(sample_repo):
    graph = DependencyGraph()
    graph.build(sample_repo)

    utils_path = os.path.join("pkg", "utils.py")
    dep = graph.get_dependencies(utils_path)
    service_path = os.path.join("pkg", "service.py")
    assert service_path in dep["imported_by"]


def test_calls_extraction(sample_repo):
    graph = DependencyGraph()
    graph.build(sample_repo)

    service_path = os.path.join("pkg", "service.py")
    dep = graph.get_dependencies(service_path)
    assert "helper" in dep["calls"]


def test_called_by_resolution(sample_repo):
    graph = DependencyGraph()
    graph.build(sample_repo)

    utils_path = os.path.join("pkg", "utils.py")
    dep = graph.get_dependencies(utils_path)
    service_path = os.path.join("pkg", "service.py")
    assert service_path in dep["called_by"], (
        f"Expected {service_path} in called_by of utils.py, got {dep['called_by']}"
    )


def test_called_by_cross_file(sample_repo):
    graph = DependencyGraph()
    graph.build(sample_repo)

    service_path = os.path.join("pkg", "service.py")
    dep = graph.get_dependencies(service_path)
    controller_path = os.path.join("pkg", "controller.py")
    assert controller_path in dep["called_by"], (
        f"Expected {controller_path} in called_by of service.py, got {dep['called_by']}"
    )


def test_impact_analysis(sample_repo):
    graph = DependencyGraph()
    graph.build(sample_repo)

    utils_path = os.path.join("pkg", "utils.py")
    impact = graph.get_impact_analysis(utils_path)
    assert impact["total_impact"] >= 1
    service_path = os.path.join("pkg", "service.py")
    assert service_path in impact["direct_dependencies"]


def test_call_chain(sample_repo):
    graph = DependencyGraph()
    graph.build(sample_repo)

    callers = graph.get_call_chain("helper")
    service_path = os.path.join("pkg", "service.py")
    assert service_path in callers


def test_transitive_call_chain(sample_repo):
    graph = DependencyGraph()
    graph.build(sample_repo)

    chains = graph.get_call_chain_transitive("helper")
    assert len(chains) >= 1
    chain_files = [step["file"] for step in chains[0]["chain"]]
    service_path = os.path.join("pkg", "service.py")
    assert service_path in chain_files


def test_symbols_extracted(sample_repo):
    graph = DependencyGraph()
    graph.build(sample_repo)

    utils_path = os.path.join("pkg", "utils.py")
    dep = graph.get_dependencies(utils_path)
    assert "helper" in dep["symbols"]
    assert "format_data" in dep["symbols"]

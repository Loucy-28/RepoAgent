import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.agent.graph import AgentGraph
from app.agent.state import AgentState, AgentPhase


def _make_state(**overrides) -> AgentState:
    defaults = {
        "task_id": "e2e-test-001",
        "repository_id": "repo-001",
        "description": "Fix off-by-one error in list slicing",
        "max_iterations": 5,
        "repo_path": "",
    }
    defaults.update(overrides)
    return AgentState(**defaults)


class TestE2EPipeline:
    @pytest.fixture
    def agent(self):
        return AgentGraph()

    @pytest.fixture
    def mock_planner(self):
        planner = AsyncMock()
        planner.create_plan = AsyncMock(return_value="1. Find the slicing function\n2. Fix the index")
        planner.dispatch_agents = AsyncMock(return_value={"search": True, "analyze": True, "test": True})
        planner.review_code = AsyncMock(return_value="- Type: Potential Bug\n- Severity: High\n- Description: Off-by-one\n- Suggestion: Fix index")
        planner.generate_edit = AsyncMock(return_value="```python\ndef slice_list(lst):\n    return lst[0:5]\n```")
        planner.generate_repair = AsyncMock(return_value="```python\ndef slice_list(lst):\n    return lst[0:6]\n```")
        planner.replan = AsyncMock(return_value="New plan: try different approach")
        return planner

    @pytest.fixture
    def mock_services(self):
        with patch("app.agent.graph.TaskService") as ts, \
             patch("app.agent.graph.CheckpointService") as cs, \
             patch("app.agent.graph.tracer") as tr, \
             patch("app.agent.graph.git_workflow") as gw:

            ts.update_status = AsyncMock()
            ts.record_step = AsyncMock()
            cs.save_checkpoint = AsyncMock()
            tr.start_span = MagicMock(return_value="span-1")
            tr.end_span = MagicMock()
            gw.create_task_branch = MagicMock(return_value={"branch": "agent/task-e2e-test-001", "success": True})
            gw.commit_changes = MagicMock(return_value={"committed": True, "sha": "abc123"})
            gw.generate_diff = MagicMock(return_value={"diff": "--- a/file\n+++ b/file\n@@ -1 +1 @@"})
            yield {"task_service": ts, "checkpoint": cs, "tracer": tr, "git": gw}

    @pytest.mark.asyncio
    async def test_full_pipeline_plan_to_completed(self, agent, mock_planner, mock_services, tmp_path):
        agent._planner = mock_planner

        src_file = tmp_path / "app" / "utils.py"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("def slice(): return [1:]", encoding="utf-8")
        file_path = str(src_file)

        with patch("app.agent.graph.search_agent") as sa, \
             patch("app.agent.graph.review_agent") as ra, \
             patch("app.agent.graph.refactor_agent") as rfa, \
             patch("app.agent.graph.validator_agent") as va:

            sa.search = AsyncMock(return_value={
                "results": [{"file_path": file_path, "code": "def slice(): return [1:]", "score": 0.9}],
                "total": 1,
            })
            ra.review = AsyncMock(return_value={
                "review": "- Type: Potential Bug\n- Severity: High\n- Description: Off-by-one\n- Suggestion: Fix",
                "findings": [{"type": "Bug", "severity": "High", "description": "Off-by-one"}],
            })
            rfa.refactor = AsyncMock(return_value={
                "edited_code": "```python\ndef slice(): return [0:]\n```",
                "original_code": "def slice(): return [1:]",
            })
            va.validate = AsyncMock(return_value={
                "success": True, "stdout": "1 passed", "stderr": "",
                "exit_code": 0, "timed_out": False, "duration_ms": 100,
            })

            state = _make_state(repo_path=str(tmp_path))
            result = await agent.run(state)

            assert result.phase == AgentPhase.WAITING_REVIEW
            assert result.test_passed is True
            assert len(result.edits) > 0
            assert result.diff != ""
            assert result.agent_routing == {"search": True, "analyze": True, "test": True}

            mock_planner.create_plan.assert_awaited_once()
            mock_planner.dispatch_agents.assert_awaited_once()
            sa.search.assert_awaited_once()
            ra.review.assert_awaited_once()
            va.validate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pipeline_test_failure_triggers_repair(self, agent, mock_planner, mock_services):
        agent._planner = mock_planner

        with patch("app.agent.graph.search_agent") as sa, \
             patch("app.agent.graph.review_agent") as ra, \
             patch("app.agent.graph.refactor_agent") as rfa, \
             patch("app.agent.graph.validator_agent") as va:

            sa.search = AsyncMock(return_value={
                "results": [{"file_path": "app/utils.py", "code": "def f(): pass", "score": 0.8}],
                "total": 1,
            })
            ra.review = AsyncMock(return_value={
                "review": "- Type: Bug\n- Severity: High\n- Description: broken\n- Suggestion: fix",
                "findings": [{"type": "Bug"}],
            })
            rfa.refactor = AsyncMock(return_value={"edited_code": "```python\ndef f(): return 1\n```"})
            va.validate = AsyncMock(side_effect=[
                {"success": False, "stdout": "", "stderr": "AssertionError",
                 "exit_code": 1, "timed_out": False, "duration_ms": 50},
                {"success": True, "stdout": "1 passed", "stderr": "",
                 "exit_code": 0, "timed_out": False, "duration_ms": 60},
            ])

            state = _make_state()
            result = await agent.run(state)

            assert result.phase == AgentPhase.WAITING_REVIEW
            assert result.test_passed is True
            assert va.validate.await_count == 2

    @pytest.mark.asyncio
    async def test_pipeline_sandbox_error_fails_fast(self, agent, mock_planner, mock_services):
        agent._planner = mock_planner

        with patch("app.agent.graph.search_agent") as sa, \
             patch("app.agent.graph.review_agent") as ra, \
             patch("app.agent.graph.refactor_agent") as rfa, \
             patch("app.agent.graph.validator_agent") as va:

            sa.search = AsyncMock(return_value={"results": [], "total": 0})
            ra.review = AsyncMock(return_value={"review": "", "findings": []})
            rfa.refactor = AsyncMock(return_value={"edited_code": ""})
            va.validate = AsyncMock(return_value={
                "success": False, "stdout": "", "stderr": "",
                "exit_code": -1, "timed_out": False, "duration_ms": 0,
                "sandbox_error": True, "error": "Docker not available",
            })

            state = _make_state()
            result = await agent.run(state)

            assert result.phase == AgentPhase.FAILED
            assert "Sandbox unavailable" in result.error

    @pytest.mark.asyncio
    async def test_pipeline_routing_skips_analyze(self, agent, mock_planner, mock_services):
        agent._planner = mock_planner
        mock_planner.dispatch_agents = AsyncMock(return_value={"search": True, "analyze": False, "test": True})

        with patch("app.agent.graph.search_agent") as sa, \
             patch("app.agent.graph.review_agent") as ra, \
             patch("app.agent.graph.validator_agent") as va:

            sa.search = AsyncMock(return_value={
                "results": [{"file_path": "app/utils.py", "code": "def f(): pass", "score": 0.8}],
                "total": 1,
            })
            va.validate = AsyncMock(return_value={
                "success": True, "stdout": "ok", "stderr": "",
                "exit_code": 0, "timed_out": False, "duration_ms": 50,
            })

            state = _make_state()
            result = await agent.run(state)

            assert ra.review.call_count == 0
            assert result.agent_routing["analyze"] is False

    @pytest.mark.asyncio
    async def test_pipeline_routing_skips_test(self, agent, mock_planner, mock_services):
        agent._planner = mock_planner
        mock_planner.dispatch_agents = AsyncMock(return_value={"search": True, "analyze": True, "test": False})

        with patch("app.agent.graph.search_agent") as sa, \
             patch("app.agent.graph.review_agent") as ra, \
             patch("app.agent.graph.refactor_agent") as rfa, \
             patch("app.agent.graph.validator_agent") as va:

            sa.search = AsyncMock(return_value={
                "results": [{"file_path": "app/utils.py", "code": "def f(): pass", "score": 0.8}],
                "total": 1,
            })
            ra.review = AsyncMock(return_value={
                "review": "- Type: Bug\n- Severity: Low\n- Description: x\n- Suggestion: y",
                "findings": [{"type": "Bug"}],
            })
            rfa.refactor = AsyncMock(return_value={"edited_code": "```python\ndef f(): return 1\n```"})

            with patch("app.agent.graph.tool_executor") as te:
                te.execute = AsyncMock(return_value={"success": True})
                state = _make_state()
                result = await agent.run(state)

            assert va.validate.call_count == 0
            assert result.phase == AgentPhase.WAITING_REVIEW
            assert result.test_passed is True

    @pytest.mark.asyncio
    async def test_pipeline_max_iterations_fails(self, agent, mock_planner, mock_services):
        agent._planner = mock_planner

        with patch("app.agent.graph.search_agent") as sa, \
             patch("app.agent.graph.review_agent") as ra, \
             patch("app.agent.graph.refactor_agent") as rfa, \
             patch("app.agent.graph.validator_agent") as va:

            sa.search = AsyncMock(return_value={"results": [], "total": 0})
            ra.review = AsyncMock(return_value={"review": "", "findings": []})
            rfa.refactor = AsyncMock(return_value={"edited_code": ""})
            va.validate = AsyncMock(return_value={
                "success": False, "stdout": "", "stderr": "fail",
                "exit_code": 1, "timed_out": False, "duration_ms": 10,
            })

            state = _make_state(max_iterations=1)
            state.iteration = 1
            result = await agent.run(state)

            assert result.phase == AgentPhase.FAILED

    @pytest.mark.asyncio
    async def test_agent_routing_serialized_in_state(self):
        state = _make_state()
        state.agent_routing = {"search": True, "analyze": False, "test": True}
        d = state.to_dict()
        assert d["agent_routing"] == {"search": True, "analyze": False, "test": True}

        restored = AgentState.from_dict(d)
        assert restored.agent_routing == {"search": True, "analyze": False, "test": True}

    @pytest.mark.asyncio
    async def test_branch_creation_failure_fails_fast(self, agent, mock_planner, mock_services):
        agent._planner = mock_planner

        with patch("app.agent.graph.git_workflow") as gw:
            gw.create_task_branch = MagicMock(return_value={
                "branch": "", "success": False, "error": "not a git repository",
            })

            state = _make_state(repo_path="/fake/repo")
            result = await agent.run(state)

            assert result.phase == AgentPhase.FAILED
            assert "Failed to create task branch" in result.error
            mock_planner.create_plan.assert_not_called()

    @pytest.mark.asyncio
    async def test_repair_loop_respects_max_iterations(self, agent, mock_planner, mock_services, tmp_path):
        agent._planner = mock_planner

        src_file = tmp_path / "mod.py"
        src_file.write_text("def f(): return 1", encoding="utf-8")
        file_path = str(src_file)

        with patch("app.agent.graph.search_agent") as sa, \
             patch("app.agent.graph.review_agent") as ra, \
             patch("app.agent.graph.refactor_agent") as rfa, \
             patch("app.agent.graph.validator_agent") as va:

            sa.search = AsyncMock(return_value={
                "results": [{"file_path": file_path, "code": "def f(): return 1", "score": 0.8}],
                "total": 1,
            })
            ra.review = AsyncMock(return_value={
                "review": "- Type: Bug\n- Severity: High\n- Description: broken\n- Suggestion: fix",
                "findings": [{"type": "Bug"}],
            })
            rfa.refactor = AsyncMock(return_value={"edited_code": "```python\ndef f(): return 2\n```"})
            va.validate = AsyncMock(return_value={
                "success": False, "stdout": "", "stderr": "AssertionError",
                "exit_code": 1, "timed_out": False, "duration_ms": 50,
            })

            state = _make_state(repo_path=str(tmp_path), max_iterations=2)
            state.iteration = 1
            result = await agent.run(state)

            assert result.phase == AgentPhase.FAILED
            assert "Max iterations" in result.error

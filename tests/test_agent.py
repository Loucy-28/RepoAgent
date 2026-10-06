import pytest
from app.agent.state import AgentState, AgentPhase


class TestAgentState:
    def test_initial_state(self):
        state = AgentState(
            task_id="test-123",
            repository_id="repo-456",
            description="Test task",
        )
        assert state.phase == AgentPhase.CREATED
        assert state.iteration == 0
        assert state.max_iterations == 5
        assert state.plan == ""
        assert state.search_results == []
        assert state.review_findings == []
        assert state.edits == []
        assert state.test_passed is False

    def test_to_dict(self):
        state = AgentState(
            task_id="test-123",
            repository_id="repo-456",
            description="Test task",
            phase=AgentPhase.SEARCHING,
            iteration=2,
        )
        d = state.to_dict()
        assert d["task_id"] == "test-123"
        assert d["phase"] == "SEARCHING"
        assert d["iteration"] == 2

    def test_from_dict(self):
        data = {
            "task_id": "test-123",
            "repository_id": "repo-456",
            "description": "Test",
            "phase": "EDITING",
            "iteration": 3,
            "max_iterations": 10,
        }
        state = AgentState.from_dict(data)
        assert state.task_id == "test-123"
        assert state.phase == AgentPhase.EDITING
        assert state.iteration == 3
        assert state.max_iterations == 10

    def test_phase_transitions(self):
        state = AgentState(
            task_id="test",
            repository_id="repo",
            description="test",
        )
        assert state.phase == AgentPhase.CREATED
        state.phase = AgentPhase.PLANNING
        assert state.phase == AgentPhase.PLANNING
        state.phase = AgentPhase.SEARCHING
        assert state.phase == AgentPhase.SEARCHING
        state.phase = AgentPhase.ANALYZING
        state.phase = AgentPhase.EDITING
        state.phase = AgentPhase.TESTING
        state.phase = AgentPhase.COMPLETED
        assert state.phase == AgentPhase.COMPLETED


class TestAgentPhase:
    def test_all_phases_exist(self):
        assert AgentPhase.CREATED
        assert AgentPhase.PLANNING
        assert AgentPhase.SEARCHING
        assert AgentPhase.ANALYZING
        assert AgentPhase.EDITING
        assert AgentPhase.TESTING
        assert AgentPhase.REPAIRING
        assert AgentPhase.COMPLETED
        assert AgentPhase.FAILED

from collections import Counter
from typing import Optional

from app.agent.state import AgentState
from app.observability.logger import get_logger

logger = get_logger(__name__)


class LoopDetector:
    SAME_TOOL_THRESHOLD = 3
    SAME_ERROR_THRESHOLD = 2
    REPEAT_TEST_FAIL_THRESHOLD = 3

    def check(self, state: AgentState) -> Optional[str]:
        reason = self._check_same_tool_loop(state)
        if reason:
            return reason

        reason = self._check_same_error_loop(state)
        if reason:
            return reason

        reason = self._check_repeat_test_failure(state)
        if reason:
            return reason

        return None

    def _check_same_tool_loop(self, state: AgentState) -> Optional[str]:
        if len(state.tool_history) < self.SAME_TOOL_THRESHOLD:
            return None

        recent = state.tool_history[-self.SAME_TOOL_THRESHOLD:]
        tools = [t["tool"] for t in recent]
        phases = [t["phase"] for t in recent]

        if len(set(tools)) == 1 and len(set(phases)) == 1:
            msg = f"Same tool '{tools[0]}' called {self.SAME_TOOL_THRESHOLD} times in phase '{phases[0]}'"
            logger.warning("loop_detected_same_tool", task_id=state.task_id, tool=tools[0], count=self.SAME_TOOL_THRESHOLD)
            return msg

        return None

    def _check_same_error_loop(self, state: AgentState) -> Optional[str]:
        if len(state.error_history) < self.SAME_ERROR_THRESHOLD:
            return None

        recent_errors = state.error_history[-self.SAME_ERROR_THRESHOLD:]
        error_msgs = [e["error"] for e in recent_errors]

        if len(set(error_msgs)) == 1:
            msg = f"Same error repeated {self.SAME_ERROR_THRESHOLD} times: {error_msgs[0][:100]}"
            logger.warning("loop_detected_same_error", task_id=state.task_id, error=error_msgs[0][:100])
            return msg

        return None

    def _check_repeat_test_failure(self, state: AgentState) -> Optional[str]:
        test_failures = [t for t in state.tool_history if t["tool"] == "run_tests" and not t["success"]]
        if len(test_failures) >= self.REPEAT_TEST_FAIL_THRESHOLD:
            msg = f"Tests failed {len(test_failures)} times consecutively"
            logger.warning("loop_detected_test_failure", task_id=state.task_id, failures=len(test_failures))
            return msg

        return None

    def build_failure_summary(self, state: AgentState) -> str:
        lines = ["=== Failure Summary ==="]
        lines.append(f"Task: {state.description}")
        lines.append(f"Iterations: {state.iteration}")
        lines.append(f"Replans: {state.replan_count}")
        lines.append("")

        if state.error_history:
            lines.append("Errors encountered:")
            for i, err in enumerate(state.error_history[-5:], 1):
                lines.append(f"  {i}. [{err['phase']}] {err['error'][:150]}")
            lines.append("")

        if state.test_result:
            lines.append("Last test result:")
            lines.append(f"  Success: {state.test_result.get('success', False)}")
            stderr = state.test_result.get("stderr", "")
            if stderr:
                lines.append(f"  Stderr: {stderr[:300]}")
            lines.append("")

        if state.edits:
            lines.append(f"Edits made: {len(state.edits)}")
            for edit in state.edits:
                lines.append(f"  - {edit.get('file_path', 'unknown')}")

        return "\n".join(lines)


loop_detector = LoopDetector()

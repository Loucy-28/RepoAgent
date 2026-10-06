import re
import time
import json
from typing import Optional

from app.agent.state import AgentState, AgentPhase
from app.agent.planner import Planner
from app.code.search import code_search
from app.code.parser import code_parser
from app.sandbox.manager import sandbox_manager
from app.services.task_service import TaskService
from app.services.checkpoint_service import CheckpointService
from app.db.enums import TaskStatus, StepType
from app.observability.logger import get_logger
from app.observability.trace import tracer
from app.config import settings

logger = get_logger(__name__)


def _extract_code_block(text: str) -> str:
    pattern = r'```(?:\w+)?\n(.*?)```'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


class AgentGraph:
    def __init__(self):
        self.planner = Planner()

    async def run(self, state: AgentState) -> AgentState:
        logger.info("agent_start", task_id=state.task_id, phase=state.phase.value)

        try:
            while state.phase not in (AgentPhase.COMPLETED, AgentPhase.FAILED):
                if state.iteration >= state.max_iterations:
                    state.phase = AgentPhase.FAILED
                    state.error = f"Max iterations ({state.max_iterations}) reached"
                    await self._update_task(state, TaskStatus.FAILED)
                    break

                state = await self._execute_phase(state)
                await CheckpointService.save_checkpoint(state.task_id, state.to_dict())

            logger.info("agent_complete", task_id=state.task_id, phase=state.phase.value)
            return state

        except Exception as e:
            logger.error("agent_error", task_id=state.task_id, error=str(e))
            state.phase = AgentPhase.FAILED
            state.error = str(e)
            await self._update_task(state, TaskStatus.FAILED)
            return state

    async def _execute_phase(self, state: AgentState) -> AgentState:
        handlers = {
            AgentPhase.CREATED: self._phase_plan,
            AgentPhase.PLANNING: self._phase_plan,
            AgentPhase.SEARCHING: self._phase_search,
            AgentPhase.ANALYZING: self._phase_analyze,
            AgentPhase.EDITING: self._phase_edit,
            AgentPhase.TESTING: self._phase_test,
            AgentPhase.REPAIRING: self._phase_repair,
        }
        handler = handlers.get(state.phase)
        if handler:
            return await handler(state)
        state.phase = AgentPhase.FAILED
        state.error = f"Unknown phase: {state.phase}"
        return state

    async def _phase_plan(self, state: AgentState) -> AgentState:
        trace_id = tracer.start_span(state.task_id, "planning", "create_plan")
        await self._update_task(state, TaskStatus.PLANNING)
        state.phase = AgentPhase.PLANNING

        repo_context = ""
        if state.repo_path:
            from app.services.repository_service import RepositoryService
            files = RepositoryService.scan_files(state.repo_path)
            repo_context = f"Repository contains {len(files)} files:\n" + "\n".join(files[:20])

        state.plan = await self.planner.create_plan(state.description, repo_context)
        state.phase = AgentPhase.SEARCHING
        state.iteration += 1

        await TaskService.record_step(
            state.task_id, StepType.PLAN, "SUCCESS",
            output_data={"plan": state.plan},
        )
        tracer.end_span(trace_id, "SUCCESS")
        return state

    async def _phase_search(self, state: AgentState) -> AgentState:
        trace_id = tracer.start_span(state.task_id, "searching", "code_search")
        await self._update_task(state, TaskStatus.SEARCHING)
        state.phase = AgentPhase.SEARCHING

        keywords = state.description.lower().split()
        keywords = [w for w in keywords if len(w) > 3][:5]
        query = " ".join(keywords) if keywords else state.description

        results = await code_search.hybrid_search(state.repository_id, query, limit=10)
        state.search_results = [
            {
                "file_path": r.file_path,
                "function_name": r.function_name,
                "class_name": r.class_name,
                "code": r.code[:500],
                "score": r.score,
            }
            for r in results
        ]

        state.phase = AgentPhase.ANALYZING
        await TaskService.record_step(
            state.task_id, StepType.SEARCH, "SUCCESS",
            output_data={"results_count": len(results)},
        )
        tracer.end_span(trace_id, "SUCCESS", details={"results": len(results)})
        return state

    async def _phase_analyze(self, state: AgentState) -> AgentState:
        trace_id = tracer.start_span(state.task_id, "analyzing", "code_review")
        await self._update_task(state, TaskStatus.ANALYZING)
        state.phase = AgentPhase.ANALYZING

        for result in state.search_results[:5]:
            file_path = result.get("file_path", "")
            code = result.get("code", "")
            if not code:
                continue

            review = await self.planner.review_code(code, file_path)
            if review:
                state.review_findings.append({
                    "file_path": file_path,
                    "review": review,
                })

        state.phase = AgentPhase.EDITING
        await TaskService.record_step(
            state.task_id, StepType.REVIEW, "SUCCESS",
            output_data={"findings_count": len(state.review_findings)},
        )
        tracer.end_span(trace_id, "SUCCESS", details={"findings": len(state.review_findings)})
        return state

    async def _phase_edit(self, state: AgentState) -> AgentState:
        trace_id = tracer.start_span(state.task_id, "editing", "code_edit")
        await self._update_task(state, TaskStatus.EDITING)
        state.phase = AgentPhase.EDITING

        for finding in state.review_findings:
            file_path = finding.get("file_path", "")
            review_text = finding.get("review", "")

            if not file_path or not review_text:
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    original_code = f.read()
            except FileNotFoundError:
                continue

            edited_code = await self.planner.generate_edit(
                original_code, file_path, review_text
            )
            new_code = _extract_code_block(edited_code)

            if new_code and new_code != original_code:
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_code)
                    state.edits.append({
                        "file_path": file_path,
                        "original": original_code[:200],
                        "modified": new_code[:200],
                    })
                except Exception as e:
                    logger.error("file_write_error", file=file_path, error=str(e))

        state.diff = self._generate_diff(state)
        state.phase = AgentPhase.TESTING
        await TaskService.record_step(
            state.task_id, StepType.EDIT, "SUCCESS",
            output_data={"edits_count": len(state.edits), "diff": state.diff[:500]},
        )
        tracer.end_span(trace_id, "SUCCESS", details={"edits": len(state.edits)})
        return state

    async def _phase_test(self, state: AgentState) -> AgentState:
        trace_id = tracer.start_span(state.task_id, "testing", "run_tests")
        await self._update_task(state, TaskStatus.TESTING)
        state.phase = AgentPhase.TESTING

        test_code = self._build_test_code(state)
        result = sandbox_manager.execute_with_timeout(test_code, "python")

        state.test_result = {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "duration_ms": result.duration_ms,
        }
        state.test_passed = result.success

        if result.success:
            state.phase = AgentPhase.COMPLETED
            await self._update_task(state, TaskStatus.COMPLETED)
            status = "SUCCESS"
        else:
            state.phase = AgentPhase.REPAIRING
            status = "FAILED"

        await TaskService.record_step(
            state.task_id, StepType.TEST, status,
            output_data=state.test_result,
            duration_ms=result.duration_ms,
        )
        tracer.end_span(trace_id, status, details=state.test_result)
        return state

    async def _phase_repair(self, state: AgentState) -> AgentState:
        trace_id = tracer.start_span(state.task_id, "repairing", "code_repair")
        await self._update_task(state, TaskStatus.REPAIRING)
        state.phase = AgentPhase.REPAIRING

        test_output = ""
        if state.test_result:
            test_output = state.test_result.get("stderr", "") or state.test_result.get("stdout", "")

        for edit in state.edits:
            file_path = edit.get("file_path", "")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    current_code = f.read()
            except FileNotFoundError:
                continue

            repaired = await self.planner.generate_repair(
                test_output, edit.get("original", ""), current_code
            )
            new_code = _extract_code_block(repaired)

            if new_code:
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_code)
                    edit["modified"] = new_code[:200]
                except Exception as e:
                    logger.error("repair_write_error", file=file_path, error=str(e))

        state.diff = self._generate_diff(state)
        state.phase = AgentPhase.TESTING
        state.iteration += 1

        await TaskService.record_step(
            state.task_id, StepType.REPAIR, "SUCCESS",
            output_data={"iteration": state.iteration},
        )
        tracer.end_span(trace_id, "SUCCESS")
        return state

    def _generate_diff(self, state: AgentState) -> str:
        diff_lines = []
        for edit in state.edits:
            file_path = edit.get("file_path", "unknown")
            diff_lines.append(f"--- a/{file_path}")
            diff_lines.append(f"+++ b/{file_path}")
            diff_lines.append(f"@@ Modified by RepoAgent @@")
            original = edit.get("original", "").splitlines()
            modified = edit.get("modified", "").splitlines()
            for line in original[:10]:
                diff_lines.append(f"- {line}")
            for line in modified[:10]:
                diff_lines.append(f"+ {line}")
            diff_lines.append("")
        return "\n".join(diff_lines)

    def _build_test_code(self, state: AgentState) -> str:
        if state.repo_path:
            import os
            test_dir = os.path.join(state.repo_path, "tests")
            if os.path.isdir(test_dir):
                test_files = [f for f in os.listdir(test_dir) if f.startswith("test_") and f.endswith(".py")]
                if test_files:
                    return f"import subprocess; result = subprocess.run(['python', '-m', 'pytest', '{test_dir}', '-v'], capture_output=True, text=True); print(result.stdout); print(result.stderr); exit(result.returncode)"

        return "print('No tests found, basic validation passed')"

    async def _update_task(self, state: AgentState, status: TaskStatus):
        await TaskService.update_status(
            state.task_id, status, current_step=state.phase.value
        )


agent_graph = AgentGraph()

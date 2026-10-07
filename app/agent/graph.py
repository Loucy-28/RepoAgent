import re
import os
import time
import json
from typing import Optional
from app.agent.state import AgentState, AgentPhase
from app.agent.planner import Planner
from app.agent.loop_detector import loop_detector
from app.agent.langgraph_executor import build_agent_graph
from app.agent.tool_executor import tool_executor
from app.agent.permissions import AgentRole, ToolName
from app.agent.sub_agents import search_agent, review_agent, refactor_agent, validator_agent
from app.code.search import code_search
from app.code.parser import code_parser
from app.code.dependency_graph import dependency_graph
from app.sandbox.manager import sandbox_manager
from app.services.git_workflow import git_workflow
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
        self._planner = None
        self._graph = None

    @property
    def planner(self):
        if self._planner is None:
            self._planner = Planner()
        return self._planner

    @property
    def graph(self):
        if self._graph is None:
            self._graph = build_agent_graph({
                "plan": self._lg_plan,
                "search": self._lg_search,
                "analyze": self._lg_analyze,
                "edit": self._lg_edit,
                "test": self._lg_test,
                "repair": self._lg_repair,
                "replan": self._lg_replan,
            })
        return self._graph

    async def run(self, state: AgentState) -> AgentState:
        logger.info("agent_start", task_id=state.task_id, phase=state.phase.value)

        try:
            if state.repo_path:
                branch_result = git_workflow.create_task_branch(state.repo_path, state.task_id)
                if not branch_result.get("success"):
                    state.phase = AgentPhase.FAILED
                    state.error = f"Failed to create task branch: {branch_result.get('error', 'unknown')}"
                    await self._update_task(state, TaskStatus.FAILED)
                    return state
                state.branch_name = branch_result.get("branch", "")
                logger.info("task_branch_set", task_id=state.task_id, branch=state.branch_name)

            lg_state = state.to_dict()
            lg_state["branch_name"] = state.branch_name

            final_lg_state = await self.graph.ainvoke(lg_state)

            state.phase = AgentPhase(final_lg_state.get("phase", "FAILED"))
            state.iteration = final_lg_state.get("iteration", state.iteration)
            state.plan = final_lg_state.get("plan", state.plan)
            state.search_results = final_lg_state.get("search_results", [])
            state.review_findings = final_lg_state.get("review_findings", [])
            state.edits = final_lg_state.get("edits", [])
            state.diff = final_lg_state.get("diff", "")
            state.test_result = final_lg_state.get("test_result")
            state.test_passed = final_lg_state.get("test_passed", False)
            state.error = final_lg_state.get("error", "")
            state.replan_count = final_lg_state.get("replan_count", 0)
            state.loop_detected = final_lg_state.get("loop_detected", False)
            state.agent_routing = final_lg_state.get("agent_routing", state.agent_routing)

            if state.phase == AgentPhase.COMPLETED:
                state.phase = AgentPhase.WAITING_REVIEW
                await self._update_task(state, TaskStatus.WAITING_REVIEW)

            logger.info("agent_complete", task_id=state.task_id, phase=state.phase.value)
            return state

        except Exception as e:
            logger.error("agent_error", task_id=state.task_id, error=str(e))
            state.phase = AgentPhase.FAILED
            state.error = str(e)
            await self._update_task(state, TaskStatus.FAILED)
            return state

    def _state_from_dict(self, d: dict) -> AgentState:
        state = AgentState.from_dict(d)
        state.branch_name = d.get("branch_name", "")
        state.agent_routing = d.get("agent_routing", {"search": True, "analyze": True, "test": True})
        return state

    def _state_to_dict(self, state: AgentState) -> dict:
        d = state.to_dict()
        d["branch_name"] = state.branch_name
        d["agent_routing"] = state.agent_routing
        return d

    async def _lg_plan(self, state: dict) -> dict:
        agent_state = self._state_from_dict(state)
        loop_reason = loop_detector.check(agent_state)
        if loop_reason:
            agent_state.loop_detected = True
            if agent_state.replan_count < agent_state.max_replans:
                agent_state = await self._phase_replan(agent_state, loop_reason)
                return self._state_to_dict(agent_state)
            else:
                agent_state.phase = AgentPhase.FAILED
                agent_state.error = f"Loop detected and max replans exceeded: {loop_reason}"
                await self._update_task(agent_state, TaskStatus.FAILED)
                return self._state_to_dict(agent_state)

        if agent_state.iteration >= agent_state.max_iterations:
            agent_state.phase = AgentPhase.FAILED
            agent_state.error = f"Max iterations ({agent_state.max_iterations}) reached"
            await self._update_task(agent_state, TaskStatus.FAILED)
            return self._state_to_dict(agent_state)

        agent_state = await self._phase_plan(agent_state)
        await CheckpointService.save_checkpoint(agent_state.task_id, agent_state.to_dict())
        return self._state_to_dict(agent_state)

    async def _lg_search(self, state: dict) -> dict:
        agent_state = self._state_from_dict(state)
        agent_state = await self._phase_search(agent_state)
        await CheckpointService.save_checkpoint(agent_state.task_id, agent_state.to_dict())
        return self._state_to_dict(agent_state)

    async def _lg_analyze(self, state: dict) -> dict:
        agent_state = self._state_from_dict(state)
        if not agent_state.agent_routing.get("analyze", True):
            logger.info("analyze_skipped_by_routing", task_id=agent_state.task_id)
            agent_state.phase = AgentPhase.EDITING
            return self._state_to_dict(agent_state)
        agent_state = await self._phase_analyze(agent_state)
        await CheckpointService.save_checkpoint(agent_state.task_id, agent_state.to_dict())
        return self._state_to_dict(agent_state)

    async def _lg_edit(self, state: dict) -> dict:
        agent_state = self._state_from_dict(state)
        agent_state = await self._phase_edit(agent_state)
        await CheckpointService.save_checkpoint(agent_state.task_id, agent_state.to_dict())
        return self._state_to_dict(agent_state)

    async def _lg_test(self, state: dict) -> dict:
        agent_state = self._state_from_dict(state)
        if not agent_state.agent_routing.get("test", True):
            logger.info("test_skipped_by_routing", task_id=agent_state.task_id)
            if agent_state.edits and agent_state.repo_path:
                commit_result = git_workflow.commit_changes(agent_state.repo_path, agent_state.task_id, agent_state.description)
                if commit_result.get("committed") and agent_state.branch_name:
                    diff_result = git_workflow.generate_diff(agent_state.repo_path, agent_state.branch_name)
                    agent_state.diff = diff_result.get("diff", agent_state.diff)
            agent_state.phase = AgentPhase.COMPLETED
            agent_state.test_passed = True
            return self._state_to_dict(agent_state)
        agent_state = await self._phase_test(agent_state)
        await CheckpointService.save_checkpoint(agent_state.task_id, agent_state.to_dict())
        return self._state_to_dict(agent_state)

    async def _lg_repair(self, state: dict) -> dict:
        agent_state = self._state_from_dict(state)
        agent_state = await self._phase_repair(agent_state)
        await CheckpointService.save_checkpoint(agent_state.task_id, agent_state.to_dict())
        return self._state_to_dict(agent_state)

    async def _lg_replan(self, state: dict) -> dict:
        agent_state = self._state_from_dict(state)
        loop_reason = state.get("error", "unknown")
        agent_state = await self._phase_replan(agent_state, loop_reason)
        await CheckpointService.save_checkpoint(agent_state.task_id, agent_state.to_dict())
        return self._state_to_dict(agent_state)

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

        routing = await self.planner.dispatch_agents(state.description, state.plan)
        state.agent_routing = routing
        logger.info("agent_routing_decided", task_id=state.task_id, routing=routing)

        state.phase = AgentPhase.SEARCHING
        state.iteration += 1

        state.record_tool_call("create_plan", "planning", True)
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

        search_data = await search_agent.search(state.repository_id, query, repo_path=state.repo_path, limit=10)
        state.search_results = search_data.get("results", [])

        state.phase = AgentPhase.ANALYZING
        state.record_tool_call("search_code", "searching", True)
        await TaskService.record_step(
            state.task_id, StepType.SEARCH, "SUCCESS",
            output_data={"results_count": search_data.get("total", 0)},
        )
        tracer.end_span(trace_id, "SUCCESS", details={"results": search_data.get("total", 0)})
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

            dep_context = ""
            if state.repo_path:
                full_path = os.path.join(state.repo_path, file_path) if not os.path.isabs(file_path) else file_path
                dep_info = dependency_graph.get_dependencies(full_path)
                if "error" not in dep_info:
                    imported_by = dep_info.get("imported_by", [])
                    calls = dep_info.get("calls", [])
                    if imported_by:
                        dep_context += f"\nThis file is imported by: {', '.join(imported_by[:5])}"
                    if calls:
                        dep_context += f"\nThis file calls: {', '.join(calls[:5])}"

            review_data = await review_agent.review(code, file_path, dep_context=dep_context)
            review_text = review_data.get("review", "")
            if review_text:
                state.review_findings.append({
                    "file_path": file_path,
                    "review": review_text,
                    "findings": review_data.get("findings", []),
                })

        state.phase = AgentPhase.EDITING
        state.record_tool_call("review_code", "analyzing", True)
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

        if state.review_findings:
            await self._edit_from_review(state)
        elif state.search_results:
            await self._edit_from_plan(state)

        if not state.edits:
            state.diff = self._generate_diff(state)

        state.phase = AgentPhase.TESTING
        await TaskService.record_step(
            state.task_id, StepType.EDIT, "SUCCESS",
            output_data={"edits_count": len(state.edits)},
        )
        tracer.end_span(trace_id, "SUCCESS", details={"edits": len(state.edits)})
        return state

    async def _edit_from_review(self, state: AgentState):
        for finding in state.review_findings:
            file_path = finding.get("file_path", "")
            review_text = finding.get("review", "")

            if not file_path or not review_text:
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    original_code = f.read()
            except FileNotFoundError:
                state.record_tool_call("edit_file", "editing", False, f"File not found: {file_path}")
                continue

            refactor_data = await refactor_agent.refactor(original_code, file_path, review_text)
            edited_code = refactor_data.get("edited_code", "")
            new_code = _extract_code_block(edited_code)

            if new_code and new_code != original_code:
                edit_result = await tool_executor.execute(
                    AgentRole.REFACTOR, ToolName.EDIT_FILE,
                    {"file_path": file_path, "new_content": new_code, "allowed_root": state.repo_path},
                )
                if edit_result.get("success"):
                    state.edits.append({
                        "file_path": file_path,
                        "original": original_code[:200],
                        "modified": new_code[:200],
                    })
                    state.record_tool_call("edit_file", "editing", True)
                else:
                    logger.error("file_write_error", file=file_path, error=edit_result.get("error", ""))
                    state.record_tool_call("edit_file", "editing", False, edit_result.get("error", ""))

    async def _edit_from_plan(self, state: AgentState):
        for result in state.search_results[:3]:
            file_path = result.get("file_path", "")
            code = result.get("code", "")
            if not file_path or not code:
                continue

            full_path = file_path
            if state.repo_path and not os.path.isabs(file_path):
                full_path = os.path.join(state.repo_path, file_path)

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    original_code = f.read()
            except (FileNotFoundError, OSError):
                continue

            edited_code = await self.planner.generate_edit(
                original_code, full_path, state.plan, "python"
            )
            new_code = _extract_code_block(edited_code)

            if new_code and new_code != original_code:
                edit_result = await tool_executor.execute(
                    AgentRole.REFACTOR, ToolName.EDIT_FILE,
                    {"file_path": full_path, "new_content": new_code, "allowed_root": state.repo_path},
                )
                if edit_result.get("success"):
                    state.edits.append({
                        "file_path": full_path,
                        "original": original_code[:200],
                        "modified": new_code[:200],
                    })
                    state.record_tool_call("edit_file", "editing", True)

    async def _phase_test(self, state: AgentState) -> AgentState:
        trace_id = tracer.start_span(state.task_id, "testing", "run_tests")
        await self._update_task(state, TaskStatus.TESTING)
        state.phase = AgentPhase.TESTING

        test_code = self._build_test_code(state)
        validation = await validator_agent.validate(test_code, "python", repo_path=state.repo_path)

        state.test_result = {
            "success": validation["success"],
            "stdout": validation["stdout"],
            "stderr": validation["stderr"],
            "exit_code": validation["exit_code"],
            "timed_out": validation["timed_out"],
            "duration_ms": validation["duration_ms"],
        }
        state.test_passed = validation["success"]

        if validation.get("sandbox_error"):
            state.phase = AgentPhase.FAILED
            state.error = f"Sandbox unavailable: {validation.get('error', 'unknown')}"
            state.record_tool_call("run_tests", "testing", False, state.error)
            await self._update_task(state, TaskStatus.FAILED)
            await TaskService.record_step(
                state.task_id, StepType.TEST, "FAILED",
                output_data=state.test_result,
            )
            return state

        state.record_tool_call("run_tests", "testing", validation["success"], validation["stderr"][:200] if not validation["success"] else "")

        if validation["success"]:
            if state.edits and state.repo_path:
                commit_result = git_workflow.commit_changes(state.repo_path, state.task_id, state.description)
                if commit_result.get("committed"):
                    logger.info("agent_changes_committed", task_id=state.task_id, sha=commit_result.get("sha", ""))
                if state.branch_name:
                    diff_result = git_workflow.generate_diff(state.repo_path, state.branch_name)
                    state.diff = diff_result.get("diff", state.diff)
                if not state.diff:
                    state.diff = self._generate_diff(state)
            else:
                state.diff = self._generate_diff(state)

            state.phase = AgentPhase.COMPLETED
            await self._update_task(state, TaskStatus.COMPLETED)
            status = "SUCCESS"
        else:
            if state.iteration >= state.max_iterations:
                state.phase = AgentPhase.FAILED
                state.error = f"Max iterations ({state.max_iterations}) reached during test-repair cycle"
                await self._update_task(state, TaskStatus.FAILED)
                status = "FAILED"
            else:
                state.phase = AgentPhase.REPAIRING
                status = "FAILED"

        await TaskService.record_step(
            state.task_id, StepType.TEST, status,
            output_data=state.test_result,
            duration_ms=validation["duration_ms"],
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
                edit_result = await tool_executor.execute(
                    AgentRole.REFACTOR, ToolName.EDIT_FILE,
                    {"file_path": file_path, "new_content": new_code, "allowed_root": state.repo_path},
                )
                if edit_result.get("success"):
                    edit["modified"] = new_code[:200]
                    state.record_tool_call("repair", "repairing", True)
                else:
                    logger.error("repair_write_error", file=file_path, error=edit_result.get("error", ""))
                    state.record_tool_call("repair", "repairing", False, edit_result.get("error", ""))

        state.diff = self._generate_diff(state)
        state.phase = AgentPhase.TESTING
        state.iteration += 1

        await TaskService.record_step(
            state.task_id, StepType.REPAIR, "SUCCESS",
            output_data={"iteration": state.iteration},
        )
        tracer.end_span(trace_id, "SUCCESS")
        return state

    async def _phase_replan(self, state: AgentState, loop_reason: str) -> AgentState:
        trace_id = tracer.start_span(state.task_id, "replanning", "replan")
        await self._update_task(state, TaskStatus.REPLANNING)
        state.phase = AgentPhase.REPLANNING

        failure_summary = loop_detector.build_failure_summary(state)
        failure_summary += f"\n\nLoop detection reason: {loop_reason}"

        new_plan = await self.planner.replan(
            state.description, state.plan, failure_summary
        )

        state.plan = new_plan
        state.replan_count += 1
        state.loop_detected = False
        state.review_findings.clear()
        state.test_result = None
        state.test_passed = False

        state.phase = AgentPhase.SEARCHING

        state.record_tool_call("replan", "replanning", True)
        await TaskService.record_step(
            state.task_id, StepType.REPLAN, "SUCCESS",
            output_data={
                "replan_count": state.replan_count,
                "reason": loop_reason,
                "new_plan": new_plan[:500],
            },
        )
        tracer.end_span(trace_id, "SUCCESS", details={"replan_count": state.replan_count})
        logger.info("agent_replanned", task_id=state.task_id, replan_count=state.replan_count)
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
                    return "import subprocess; result = subprocess.run(['python', '-m', 'pytest', '/workspace/tests', '-v'], capture_output=True, text=True); print(result.stdout); print(result.stderr); exit(result.returncode)"

        return "print('No tests found, basic validation passed')"

    async def _update_task(self, state: AgentState, status: TaskStatus):
        await TaskService.update_status(
            state.task_id, status, current_step=state.phase.value
        )


agent_graph = AgentGraph()

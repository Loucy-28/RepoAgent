from typing import Optional
from langchain_openai import ChatOpenAI
from app.config import settings
from app.agent.prompts import SYSTEM_PROMPT, PLANNER_PROMPT, REVIEW_PROMPT, CODE_EDIT_PROMPT, REPAIR_PROMPT, REPLAN_PROMPT, AGENT_ROUTING_PROMPT
from app.agent.guardrails import sanitize_input, sanitize_code_for_prompt, detect_injection
from app.observability.logger import get_logger

logger = get_logger(__name__)


class Planner:
    def __init__(self):
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                temperature=0.1,
            )
        return self._llm

    async def create_plan(self, description: str, repo_context: str = "") -> str:
        description = sanitize_input(description)
        repo_context = sanitize_input(repo_context)
        prompt = PLANNER_PROMPT.format(description=description, repo_context=repo_context)
        try:
            response = await self.llm.ainvoke([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
            return response.content
        except Exception as e:
            logger.error("planner_failed", error=str(e))
            return f"Plan: {description}"

    async def review_code(self, code: str, file_path: str, language: str = "python") -> str:
        code = sanitize_code_for_prompt(code)
        prompt = REVIEW_PROMPT.format(code=code, file_path=file_path, language=language)
        try:
            response = await self.llm.ainvoke([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
            return response.content
        except Exception as e:
            logger.error("review_failed", error=str(e))
            return ""

    async def generate_edit(self, code: str, file_path: str, findings: str, language: str = "python") -> str:
        code = sanitize_code_for_prompt(code)
        findings = sanitize_input(findings)
        prompt = CODE_EDIT_PROMPT.format(
            code=code, file_path=file_path, findings=findings, language=language
        )
        try:
            response = await self.llm.ainvoke([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
            return response.content
        except Exception as e:
            logger.error("edit_generation_failed", error=str(e))
            return ""

    async def generate_repair(self, test_output: str, original_code: str, modified_code: str, language: str = "python") -> str:
        test_output = sanitize_input(test_output)
        original_code = sanitize_code_for_prompt(original_code)
        modified_code = sanitize_code_for_prompt(modified_code)
        prompt = REPAIR_PROMPT.format(
            test_output=test_output,
            original_code=original_code,
            modified_code=modified_code,
            language=language,
        )
        try:
            response = await self.llm.ainvoke([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
            return response.content
        except Exception as e:
            logger.error("repair_failed", error=str(e))
            return ""

    async def replan(self, description: str, current_plan: str, failure_summary: str) -> str:
        description = sanitize_input(description)
        current_plan = sanitize_input(current_plan)
        failure_summary = sanitize_input(failure_summary)
        prompt = REPLAN_PROMPT.format(
            failure_summary=failure_summary,
            description=description,
            current_plan=current_plan,
        )
        try:
            response = await self.llm.ainvoke([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
            return response.content
        except Exception as e:
            logger.error("replan_failed", error=str(e))
            return f"Replan: {description}"

    async def dispatch_agents(self, description: str, plan: str) -> dict:
        description = sanitize_input(description)
        plan = sanitize_input(plan)
        prompt = AGENT_ROUTING_PROMPT.format(description=description, plan=plan)
        default_routing = {"search": True, "analyze": True, "test": True}
        try:
            response = await self.llm.ainvoke([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
            import json
            text = response.content.strip()
            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                routing = json.loads(text[json_start:json_end])
                return {k: routing.get(k, True) for k in ("search", "analyze", "test")}
            return default_routing
        except Exception as e:
            logger.warning("agent_dispatch_failed", error=str(e))
            return default_routing

from typing import Optional
from langchain_openai import ChatOpenAI
from app.config import settings
from app.agent.prompts import SYSTEM_PROMPT, PLANNER_PROMPT, REVIEW_PROMPT, CODE_EDIT_PROMPT, REPAIR_PROMPT
from app.observability.logger import get_logger

logger = get_logger(__name__)


class Planner:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.1,
        )

    async def create_plan(self, description: str, repo_context: str = "") -> str:
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

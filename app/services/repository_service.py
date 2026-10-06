import os
import uuid
import shutil
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Repository
from app.db.enums import CodeLanguage
from app.db.session import async_session_factory
from app.observability.logger import get_logger

logger = get_logger(__name__)


class RepositoryService:
    REPOS_DIR = "data/repositories"

    @staticmethod
    async def create_repository(name: str, path: str, language: str = "python") -> Repository:
        async with async_session_factory() as session:
            repo = Repository(
                name=name,
                path=path,
                language=CodeLanguage(language) if language in [e.value for e in CodeLanguage] else CodeLanguage.UNKNOWN,
            )
            session.add(repo)
            await session.commit()
            await session.refresh(repo)
            logger.info("repository_created", repo_id=str(repo.id), name=name)
            return repo

    @staticmethod
    async def get_repository(repo_id: str) -> Optional[Repository]:
        async with async_session_factory() as session:
            result = await session.execute(select(Repository).where(Repository.id == uuid.UUID(repo_id)))
            return result.scalar_one_or_none()

    @staticmethod
    async def list_repositories() -> list[Repository]:
        async with async_session_factory() as session:
            result = await session.execute(select(Repository).order_by(Repository.created_at.desc()))
            return list(result.scalars().all())

    @staticmethod
    async def delete_repository(repo_id: str) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(select(Repository).where(Repository.id == uuid.UUID(repo_id)))
            repo = result.scalar_one_or_none()
            if not repo:
                return False
            await session.delete(repo)
            await session.commit()
            logger.info("repository_deleted", repo_id=repo_id)
            return True

    @staticmethod
    def scan_files(repo_path: str, extensions: Optional[list[str]] = None) -> list[str]:
        if extensions is None:
            extensions = [".py", ".java"]
        files = []
        for root, _, filenames in os.walk(repo_path):
            if "__pycache__" in root or ".git" in root or "node_modules" in root:
                continue
            for f in filenames:
                if any(f.endswith(ext) for ext in extensions):
                    files.append(os.path.join(root, f))
        return files

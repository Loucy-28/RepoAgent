import uuid
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CodeChunk
from app.db.enums import CodeLanguage
from app.db.session import async_session_factory
from app.code.parser import code_parser, ParsedFile
from app.code.dependency_graph import dependency_graph
from app.services.repository_service import RepositoryService
from app.observability.logger import get_logger

logger = get_logger(__name__)


class CodeIndexer:
    async def index_repository(self, repo_id: str, repo_path: str, language: str = "python") -> int:
        async with async_session_factory() as session:
            await session.execute(
                delete(CodeChunk).where(CodeChunk.repository_id == uuid.UUID(repo_id))
            )
            await session.commit()

        files = RepositoryService.scan_files(repo_path)
        chunk_count = 0

        for file_path in files:
            parsed = code_parser.parse_file(file_path)
            if not parsed:
                continue

            if parsed.symbols:
                for symbol in parsed.symbols:
                    await self._save_chunk(
                        repo_id=repo_id,
                        file_path=file_path,
                        class_name=symbol.parent if symbol.kind == "method" else (symbol.name if symbol.kind == "class" else ""),
                        function_name=symbol.name if symbol.kind in ("function", "method") else "",
                        language=language,
                        code=symbol.code,
                        start_line=symbol.start_line,
                        end_line=symbol.end_line,
                        metadata={"kind": symbol.kind, "args": symbol.args, "decorators": symbol.decorators},
                    )
                    chunk_count += 1
            else:
                await self._save_chunk(
                    repo_id=repo_id,
                    file_path=file_path,
                    language=language,
                    code=parsed.raw_code,
                    start_line=1,
                    end_line=parsed.total_lines,
                    metadata={"kind": "file", "imports": parsed.imports},
                )
                chunk_count += 1

        dep_count = dependency_graph.build(repo_path)
        logger.info("index_complete", repo_id=repo_id, chunks=chunk_count, files=len(files), dep_nodes=dep_count)
        return chunk_count

    async def _save_chunk(
        self,
        repo_id: str,
        file_path: str,
        class_name: str = "",
        function_name: str = "",
        language: str = "python",
        code: str = "",
        start_line: int = 0,
        end_line: int = 0,
        metadata: Optional[dict] = None,
    ):
        async with async_session_factory() as session:
            chunk = CodeChunk(
                repository_id=uuid.UUID(repo_id),
                file_path=file_path,
                class_name=class_name,
                function_name=function_name,
                language=CodeLanguage(language) if language in [e.value for e in CodeLanguage] else CodeLanguage.UNKNOWN,
                code=code,
                start_line=start_line,
                end_line=end_line,
                metadata_=metadata or {},
            )
            session.add(chunk)
            await session.commit()


code_indexer = CodeIndexer()

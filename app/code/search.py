import re
import math
from typing import Optional
from dataclasses import dataclass

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CodeChunk
from app.db.session import async_session_factory
from app.observability.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SearchResult:
    file_path: str
    class_name: str
    function_name: str
    code: str
    start_line: int
    end_line: int
    score: float
    language: str = ""


class CodeSearch:
    async def keyword_search(self, repo_id: str, query: str, limit: int = 10) -> list[SearchResult]:
        async with async_session_factory() as session:
            terms = query.lower().split()
            conditions = []
            for term in terms:
                conditions.append(CodeChunk.code.ilike(f"%{term}%"))
                conditions.append(CodeChunk.function_name.ilike(f"%{term}%"))
                conditions.append(CodeChunk.class_name.ilike(f"%{term}%"))
                conditions.append(CodeChunk.file_path.ilike(f"%{term}%"))

            stmt = (
                select(CodeChunk)
                .where(CodeChunk.repository_id == repo_id)
                .where(or_(*conditions))
                .limit(limit * 2)
            )
            result = await session.execute(stmt)
            chunks = result.scalars().all()

        scored = []
        for chunk in chunks:
            score = self._bm25_score(chunk, terms)
            scored.append(SearchResult(
                file_path=chunk.file_path,
                class_name=chunk.class_name or "",
                function_name=chunk.function_name or "",
                code=chunk.code,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                score=score,
                language=chunk.language.value if chunk.language else "",
            ))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:limit]

    async def semantic_search(self, repo_id: str, query: str, limit: int = 10) -> list[SearchResult]:
        """Placeholder for embedding-based semantic search.

        Currently delegates to keyword_search with query expansion until
        a real embedding model is integrated.
        """
        expanded = query + " " + " ".join(t + "s" for t in query.split() if len(t) > 2)
        return await self.keyword_search(repo_id, expanded, limit)

    async def hybrid_search(self, repo_id: str, query: str, limit: int = 10) -> list[SearchResult]:
        """Combines keyword and semantic search via reciprocal rank fusion.

        Note: semantic_search is currently a keyword-based placeholder.
        True vector search requires embedding model integration.
        """
        keyword_results = await self.keyword_search(repo_id, query, limit * 2)
        semantic_results = await self.semantic_search(repo_id, query, limit * 2)

        all_results = {}
        for i, r in enumerate(keyword_results):
            key = f"{r.file_path}:{r.start_line}"
            all_results[key] = SearchResult(
                file_path=r.file_path,
                class_name=r.class_name,
                function_name=r.function_name,
                code=r.code,
                start_line=r.start_line,
                end_line=r.end_line,
                score=0,
                language=r.language,
            )
            rank_score = 1.0 / (i + 1)
            all_results[key].score += rank_score

        for i, r in enumerate(semantic_results):
            key = f"{r.file_path}:{r.start_line}"
            if key not in all_results:
                all_results[key] = SearchResult(
                    file_path=r.file_path,
                    class_name=r.class_name,
                    function_name=r.function_name,
                    code=r.code,
                    start_line=r.start_line,
                    end_line=r.end_line,
                    score=0,
                    language=r.language,
                )
            rank_score = 1.0 / (i + 1)
            all_results[key].score += rank_score

        results = sorted(all_results.values(), key=lambda x: x.score, reverse=True)
        return results[:limit]

    def _bm25_score(self, chunk: CodeChunk, terms: list[str], k1: float = 1.5, b: float = 0.75) -> float:
        text = f"{chunk.code} {chunk.function_name} {chunk.class_name} {chunk.file_path}".lower()
        doc_len = len(text.split())
        avg_dl = 200
        score = 0.0
        for term in terms:
            tf = text.count(term)
            if tf == 0:
                continue
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * doc_len / avg_dl)
            score += numerator / denominator
        return score


code_search = CodeSearch()

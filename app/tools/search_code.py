from typing import Optional
from app.code.search import code_search, SearchResult
from app.observability.logger import get_logger

logger = get_logger(__name__)


async def search_code(repo_id: str, query: str, limit: int = 10) -> list[dict]:
    results = await code_search.hybrid_search(repo_id, query, limit)
    return [
        {
            "file_path": r.file_path,
            "function_name": r.function_name,
            "class_name": r.class_name,
            "code": r.code[:500],
            "score": r.score,
            "language": r.language,
        }
        for r in results
    ]

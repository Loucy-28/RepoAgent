from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.repository_service import RepositoryService
from app.code.indexer import code_indexer
from app.db.models import Repository
from app.observability.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/repositories", tags=["repositories"])


class CreateRepositoryRequest(BaseModel):
    name: str
    path: str
    language: str = "python"


class RepositoryResponse(BaseModel):
    id: str
    name: str
    path: str
    language: str
    created_at: str

    model_config = {"from_attributes": True}


class IndexResponse(BaseModel):
    repository_id: str
    chunks_indexed: int
    status: str


def _repo_to_response(repo: Repository) -> RepositoryResponse:
    return RepositoryResponse(
        id=str(repo.id),
        name=repo.name,
        path=repo.path,
        language=repo.language.value if repo.language else "unknown",
        created_at=repo.created_at.isoformat() if repo.created_at else "",
    )


@router.post("", response_model=RepositoryResponse, status_code=201)
async def create_repository(req: CreateRepositoryRequest):
    repo = await RepositoryService.create_repository(
        name=req.name,
        path=req.path,
        language=req.language,
    )
    return _repo_to_response(repo)


@router.get("", response_model=list[RepositoryResponse])
async def list_repositories():
    repos = await RepositoryService.list_repositories()
    return [_repo_to_response(r) for r in repos]


@router.get("/{repo_id}", response_model=RepositoryResponse)
async def get_repository(repo_id: str):
    repo = await RepositoryService.get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return _repo_to_response(repo)


@router.delete("/{repo_id}")
async def delete_repository(repo_id: str):
    success = await RepositoryService.delete_repository(repo_id)
    if not success:
        raise HTTPException(status_code=404, detail="Repository not found")
    return {"message": "Repository deleted", "repo_id": repo_id}


@router.post("/{repo_id}/index", response_model=IndexResponse)
async def index_repository(repo_id: str):
    repo = await RepositoryService.get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    chunks = await code_indexer.index_repository(
        repo_id=str(repo.id),
        repo_path=repo.path,
        language=repo.language.value if repo.language else "python",
    )

    return IndexResponse(
        repository_id=str(repo.id),
        chunks_indexed=chunks,
        status="completed",
    )

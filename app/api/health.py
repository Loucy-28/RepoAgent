from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "repo-agent",
        "version": "1.0.0",
    }

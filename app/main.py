from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.tasks import router as tasks_router
from app.api.repositories import router as repositories_router
from app.api.metrics import router as metrics_router
from app.db.session import init_db, close_db
from app.services.redis_client import get_redis, close_redis
from app.observability.logger import setup_logger, get_logger

setup_logger()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_repo_agent")
    await init_db()
    await get_redis()
    logger.info("repo_agent_started")
    yield
    logger.info("shutting_down_repo_agent")
    await close_db()
    await close_redis()
    logger.info("repo_agent_stopped")


app = FastAPI(
    title="RepoAgent",
    description="Enterprise Coding Agent for Code Review and Automated Refactoring",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(tasks_router)
app.include_router(repositories_router)
app.include_router(metrics_router)

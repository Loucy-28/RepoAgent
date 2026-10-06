import uuid
import time
from typing import Optional
from dataclasses import dataclass, field, asdict

from app.db.session import async_session_factory
from app.db.models import ExecutionRecord
from app.observability.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SpanData:
    trace_id: str
    task_id: str
    step: str
    tool: str = ""
    start_time: float = field(default_factory=time.time)
    duration_ms: int = 0
    status: str = "RUNNING"
    error: str = ""
    details: dict = field(default_factory=dict)


class Tracer:
    def __init__(self):
        self._spans: dict[str, SpanData] = {}

    def start_span(self, task_id: str, step: str, tool: str = "") -> str:
        trace_id = uuid.uuid4().hex[:12]
        span = SpanData(trace_id=trace_id, task_id=str(task_id), step=step, tool=tool)
        self._spans[trace_id] = span
        logger.info("span_started", trace_id=trace_id, task_id=str(task_id), step=step, tool=tool)
        return trace_id

    def end_span(self, trace_id: str, status: str = "SUCCESS", error: str = "", details: Optional[dict] = None):
        span = self._spans.get(trace_id)
        if not span:
            return
        span.duration_ms = int((time.time() - span.start_time) * 1000)
        span.status = status
        span.error = error
        if details:
            span.details = details
        logger.info(
            "span_ended",
            trace_id=trace_id,
            task_id=span.task_id,
            step=span.step,
            duration_ms=span.duration_ms,
            status=status,
        )
        self._persist(span)
        del self._spans[trace_id]

    def _persist(self, span: SpanData):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._save_record(span))
        except RuntimeError:
            pass

    async def _save_record(self, span: SpanData):
        try:
            async with async_session_factory() as session:
                record = ExecutionRecord(
                    task_id=uuid.UUID(span.task_id),
                    trace_id=span.trace_id,
                    step=span.step,
                    tool=span.tool,
                    duration_ms=span.duration_ms,
                    status=span.status,
                    error=span.error,
                    details=span.details,
                )
                session.add(record)
                await session.commit()
        except Exception as e:
            logger.error("trace_persist_failed", error=str(e))


tracer = Tracer()

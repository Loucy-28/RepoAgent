import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Integer, Float, DateTime, Enum, ForeignKey, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship

from app.db.enums import TaskStatus, StepType, CodeLanguage


class Base(DeclarativeBase):
    pass


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    path = Column(Text, nullable=False)
    language = Column(Enum(CodeLanguage), default=CodeLanguage.PYTHON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tasks = relationship("Task", back_populates="repository", cascade="all, delete-orphan")
    code_chunks = relationship("CodeChunk", back_populates="repository", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id = Column(UUID(as_uuid=True), ForeignKey("repositories.id"), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.CREATED, nullable=False)
    current_step = Column(String(100), default="")
    iteration = Column(Integer, default=0)
    max_iterations = Column(Integer, default=5)
    result = Column(JSON, default=dict)
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    repository = relationship("Repository", back_populates="tasks")
    steps = relationship("AgentStep", back_populates="task", cascade="all, delete-orphan", order_by="AgentStep.created_at")
    execution_records = relationship("ExecutionRecord", back_populates="task", cascade="all, delete-orphan")


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    step_type = Column(Enum(StepType), nullable=False)
    status = Column(String(50), nullable=False, default="PENDING")
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, default=dict)
    error = Column(Text, default="")
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    task = relationship("Task", back_populates="steps")


class CodeChunk(Base):
    __tablename__ = "code_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id = Column(UUID(as_uuid=True), ForeignKey("repositories.id"), nullable=False)
    file_path = Column(Text, nullable=False)
    class_name = Column(String(255), default="")
    function_name = Column(String(255), default="")
    language = Column(Enum(CodeLanguage), default=CodeLanguage.PYTHON)
    code = Column(Text, nullable=False)
    start_line = Column(Integer, default=0)
    end_line = Column(Integer, default=0)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    repository = relationship("Repository", back_populates="code_chunks")


class ExecutionRecord(Base):
    __tablename__ = "execution_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    trace_id = Column(String(100), nullable=False)
    step = Column(String(100), nullable=False)
    tool = Column(String(100), default="")
    duration_ms = Column(Integer, default=0)
    status = Column(String(50), nullable=False)
    error = Column(Text, default="")
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    task = relationship("Task", back_populates="execution_records")

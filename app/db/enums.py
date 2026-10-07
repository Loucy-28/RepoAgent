import enum


class TaskStatus(str, enum.Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    SEARCHING = "SEARCHING"
    ANALYZING = "ANALYZING"
    EDITING = "EDITING"
    TESTING = "TESTING"
    REPAIRING = "REPAIRING"
    REPLANNING = "REPLANNING"
    WAITING_REVIEW = "WAITING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MERGED = "MERGED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepType(str, enum.Enum):
    PLAN = "PLAN"
    SEARCH = "SEARCH"
    REVIEW = "REVIEW"
    EDIT = "EDIT"
    TEST = "TEST"
    REPAIR = "REPAIR"
    REPLAN = "REPLAN"


class CodeLanguage(str, enum.Enum):
    PYTHON = "python"
    JAVA = "java"
    UNKNOWN = "unknown"

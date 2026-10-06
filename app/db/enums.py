import enum


class TaskStatus(str, enum.Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    SEARCHING = "SEARCHING"
    ANALYZING = "ANALYZING"
    EDITING = "EDITING"
    TESTING = "TESTING"
    REPAIRING = "REPAIRING"
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


class CodeLanguage(str, enum.Enum):
    PYTHON = "python"
    JAVA = "java"
    UNKNOWN = "unknown"

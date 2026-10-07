from dataclasses import dataclass, field


@dataclass
class BenchmarkCase:
    id: str
    name: str
    description: str
    category: str
    difficulty: str
    expected_phases: list[str] = field(default_factory=list)
    expected_tools: list[str] = field(default_factory=list)
    success_criteria: str = ""


BENCHMARK_CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        id="bench-001",
        name="fix_off_by_one",
        description="Fix an off-by-one error in a list slicing function where the last element is excluded incorrectly",
        category="bug_fix",
        difficulty="easy",
        expected_phases=["PLANNING", "SEARCHING", "ANALYZING", "EDITING", "TESTING"],
        expected_tools=["search_code", "read_file", "edit_file"],
        success_criteria="Agent identifies the slicing bug and corrects the index",
    ),
    BenchmarkCase(
        id="bench-002",
        name="add_missing_function",
        description="Add a calculate_average function to a math_utils module that computes the mean of a list of numbers",
        category="feature_add",
        difficulty="easy",
        expected_phases=["PLANNING", "SEARCHING", "EDITING", "TESTING"],
        expected_tools=["search_code", "read_file", "edit_file"],
        success_criteria="Function is added with correct signature and implementation",
    ),
    BenchmarkCase(
        id="bench-003",
        name="rename_variable_refactor",
        description="Rename the variable 'usr_data' to 'user_data' across all occurrences in the module for clarity",
        category="refactor",
        difficulty="easy",
        expected_phases=["PLANNING", "SEARCHING", "ANALYZING", "EDITING"],
        expected_tools=["search_code", "read_file", "edit_file"],
        success_criteria="All occurrences renamed consistently without breaking references",
    ),
    BenchmarkCase(
        id="bench-004",
        name="detect_sql_injection",
        description="Review a database query function that concatenates user input directly into SQL and fix the injection vulnerability",
        category="security",
        difficulty="medium",
        expected_phases=["PLANNING", "SEARCHING", "ANALYZING", "EDITING", "TESTING"],
        expected_tools=["search_code", "read_file", "review_code", "edit_file"],
        success_criteria="Agent identifies SQL injection risk and replaces with parameterized query",
    ),
    BenchmarkCase(
        id="bench-005",
        name="add_error_handling",
        description="Add proper try-except error handling to a file processing function that currently has no error handling for missing files",
        category="robustness",
        difficulty="medium",
        expected_phases=["PLANNING", "SEARCHING", "ANALYZING", "EDITING"],
        expected_tools=["search_code", "read_file", "edit_file"],
        success_criteria="Error handling added with appropriate exception types and logging",
    ),
    BenchmarkCase(
        id="bench-006",
        name="add_docstrings",
        description="Add comprehensive docstrings to all public functions in a module that currently has no documentation",
        category="documentation",
        difficulty="easy",
        expected_phases=["PLANNING", "SEARCHING", "ANALYZING", "EDITING"],
        expected_tools=["search_code", "read_file", "edit_file"],
        success_criteria="All public functions have docstrings with description, params, and return type",
    ),
    BenchmarkCase(
        id="bench-007",
        name="extract_method",
        description="A function has grown too long with multiple responsibilities. Extract the validation logic into a separate helper function",
        category="refactor",
        difficulty="medium",
        expected_phases=["PLANNING", "SEARCHING", "ANALYZING", "EDITING", "TESTING"],
        expected_tools=["search_code", "read_file", "review_code", "edit_file"],
        success_criteria="Validation logic extracted to a well-named helper, original function simplified",
    ),
    BenchmarkCase(
        id="bench-008",
        name="add_type_hints",
        description="Add proper type hints to a Python module that has no type annotations, including function signatures and class attributes",
        category="type_safety",
        difficulty="medium",
        expected_phases=["PLANNING", "SEARCHING", "EDITING"],
        expected_tools=["search_code", "read_file", "edit_file"],
        success_criteria="All functions have parameter and return type annotations",
    ),
    BenchmarkCase(
        id="bench-009",
        name="fix_race_condition",
        description="A shared counter is incremented from multiple async tasks without synchronization. Add a lock to prevent race conditions",
        category="concurrency",
        difficulty="hard",
        expected_phases=["PLANNING", "SEARCHING", "ANALYZING", "EDITING", "TESTING"],
        expected_tools=["search_code", "read_file", "review_code", "edit_file", "run_tests"],
        success_criteria="AsyncIO lock added around shared state mutation",
    ),
    BenchmarkCase(
        id="bench-010",
        name="add_unit_test",
        description="Write unit tests for a string utility module that has no test coverage, covering edge cases like empty strings and unicode",
        category="testing",
        difficulty="medium",
        expected_phases=["PLANNING", "SEARCHING", "ANALYZING", "EDITING", "TESTING"],
        expected_tools=["search_code", "read_file", "edit_file", "run_tests"],
        success_criteria="Test file created with tests for normal cases, edge cases, and error cases",
    ),
]


def get_benchmark_case(case_id: str) -> BenchmarkCase | None:
    for case in BENCHMARK_CASES:
        if case.id == case_id:
            return case
    return None


def get_benchmark_cases_by_category(category: str) -> list[BenchmarkCase]:
    return [c for c in BENCHMARK_CASES if c.category == category]


def get_all_categories() -> list[str]:
    return sorted(set(c.category for c in BENCHMARK_CASES))

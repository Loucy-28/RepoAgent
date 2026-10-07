# RepoAgent v2.0

**Enterprise Coding Agent for Code Review and Automated Refactoring**

> An AI-powered multi-agent coding platform that understands codebases, identifies code issues, proposes refactoring plans, modifies code automatically, and validates changes in an isolated Docker sandbox with test-driven repair loops. Features loop detection with auto-replan, dependency graph analysis, human review workflows with git branch management, and a built-in benchmark system.

## What's New in v2.0

| Feature | Description |
|---------|-------------|
| Loop Detection & Replan | Detects agent loops (same tool >= 3x, same error >= 2x) and triggers intelligent replanning |
| Multi-Agent Architecture | Orchestrator delegates to Search, Review, Refactor, and Validator agents with isolated tool permissions |
| Dependency Graph | AST-based code dependency analysis with impact analysis and call chain tracking |
| Human Review Workflow | Task state machine extended with WAITING_REVIEW -> APPROVED -> MERGED flow |
| Git Branch Workflow | Each task creates a branch (`agent/task-{id}`), commits changes, and supports merge-to-main |
| Benchmark System | 10 predefined benchmark cases across 8 categories with metrics collection and API |

## Architecture

```
                       RepoAgent v2.0
                            |
            +---------------+---------------+
            |               |               |
            v               v               v
      Multi-Agent      Code Intelligence   Runtime
            |               |               |
   +--------+--------+     v               v
   |   |    |    |   |  Dependency       Docker
   v   v    v    v   v  Graph             Sandbox
 Search Review Refactor Validator         Test
   |               |               |
   +-------+-------+-------+-------+
           |               |
           v               v
     Loop Detection   Git Workflow
     Auto Replan      Branch / Merge
           |               |
           +-------+-------+
                   |
                   v
             Backend Layer
                   |
          +--------+--------+
          v        v        v
       FastAPI   Redis   PostgreSQL
          |
          v
    Observability + Benchmark
```

## Core Workflow

```
User submits task
      |
      v
 Create Branch (agent/task-{id})  ──FAIL──>  FAILED
      |
      v (success)
 Agent Planner  -->  Understand task + LLM agent dispatch
      |
      v
 Code Search (SearchAgent)  -->  Retrieve relevant code
      |
      v
 Code Review (ReviewAgent)  -->  Find issues + dependency context
      |                            (skippable via LLM routing)
      v
 Edit Code (RefactorAgent)  -->  Generate fixes (via ToolExecutor)
      |
      v
 Docker Sandbox (ValidatorAgent)  -->  Compile / Test
      |
   +--+--+
   |     |
 FAIL   PASS
   |     |
   v     v
 iteration < max?   Commit Changes to Branch
  ├─Y─> Repair          |
  └─N─> FAILED          |
   |                    |
   +--------------------+
      |
      v
 WAITING_REVIEW  -->  Human Approval
      |
   +--+--+
   |     |
APPROVE  REJECT
   |
   v
 MERGE to main
```

## Agent State Machine

```
CREATED -> PLANNING -> SEARCHING -> ANALYZING -> EDITING -> TESTING
                                                              |
                                                        +-----+-----+
                                                        |           |
                                                      PASS        FAIL
                                                        |           |
                                                        v           v
                                                    COMPLETED   iteration < max?
                                                                   |       |
                                                                  Yes     No
                                                                   |       |
                                                                   v       v
                                                               REPAIRING  FAILED
                                                                   |
                                                                   v
                                                                TESTING
                                                                (retry)

Loop detected? -> REPLANNING (up to 2 replans) -> SEARCHING (retry)
COMPLETED -> WAITING_REVIEW -> APPROVED -> MERGED
                            -> REJECTED
```

| Phase | Description |
|-------|-------------|
| `CREATED` | Task created, awaiting execution |
| `PLANNING` | Agent understands task and creates execution plan |
| `SEARCHING` | Search codebase for relevant code |
| `ANALYZING` | Review and analyze retrieved code with dependency context |
| `EDITING` | Modify code based on review findings |
| `TESTING` | Run tests in Docker sandbox |
| `REPAIRING` | Test failed, agent analyzes errors and fixes code |
| `REPLANNING` | Loop detected, agent generates a fundamentally different plan |
| `WAITING_REVIEW` | Task completed, awaiting human review |
| `APPROVED` | Reviewer approved the changes |
| `REJECTED` | Reviewer rejected the changes |
| `MERGED` | Changes merged to main branch |
| `COMPLETED` | Tests passed, task done |
| `FAILED` | Max iterations exceeded or unrecoverable error |

## Multi-Agent Architecture

After planning, the orchestrator uses an LLM-based routing decision to dynamically select which specialist agents to invoke for each task. For example, a simple documentation task may skip the ReviewAgent, while a complex refactor engages all agents. All tool calls are routed through the unified `ToolExecutor` permission gateway.

| Agent | Role | Allowed Tools |
|-------|------|---------------|
| **Orchestrator** | Planning, routing & coordination | `create_plan`, `replan` |
| **SearchAgent** | Code retrieval & dependency context | `search_code`, `read_file`, `list_files`, `get_dependencies` |
| **ReviewAgent** | Code review & analysis (LLM-selected) | `search_code`, `read_file`, `get_dependencies`, `review_code` |
| **RefactorAgent** | Code modification | `read_file`, `edit_file`, `git_diff` |
| **ValidatorAgent** | Test execution (LLM-selected) | `run_tests`, `read_file` |

### Loop Detection

The system monitors agent behavior and detects three types of loops:

| Pattern | Threshold | Action |
|---------|-----------|--------|
| Same tool called repeatedly | >= 3 consecutive calls | Trigger replan |
| Same error recurring | >= 2 repetitions | Trigger replan |
| Test fails after repair | >= 3 attempts | Trigger replan |

When a loop is detected and `replan_count < max_replans`, the agent:
1. Builds a failure summary of what went wrong
2. Generates a fundamentally different plan via LLM
3. Resets review findings and retries from the search phase

## Dependency Graph

The code intelligence layer builds a full dependency graph during indexing:

```python
# Build graph for a repository
dependency_graph.build(repo_path)

# Get dependencies for a file
deps = dependency_graph.get_dependencies("/path/to/file.py")
# -> {"imports": [...], "imported_by": [...], "calls": [...], "called_by": [...]}

# Impact analysis: what breaks if this file changes?
impact = dependency_graph.get_impact_analysis("/path/to/file.py")
# -> {"direct": [...], "transitive": [...]}
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI, Pydantic |
| Database | PostgreSQL, SQLAlchemy (async) |
| Cache/Lock | Redis |
| Agent | LangGraph, LangChain, OpenAI |
| Code Analysis | AST Parser (Python), Regex Parser (Java) |
| Dependency Graph | AST-based (Python), Regex-based (Java) |
| Sandbox | Docker (resource-limited, network-isolated) |
| Git Workflow | subprocess (branch, commit, merge) |
| Observability | Structured Logging (structlog), Distributed Tracing |
| Benchmark | Built-in runner with metrics collection |
| Testing | pytest, pytest-asyncio |

## Project Structure

```
repo-agent/
|
+-- app/
|   +-- main.py                  # FastAPI application entry
|   +-- config.py                # Pydantic settings
|   |
|   +-- api/
|   |   +-- health.py            # Health check endpoint
|   |   +-- tasks.py             # Task CRUD + agent execution + review workflow
|   |   +-- repositories.py      # Repository management + indexing + dependencies
|   |   +-- metrics.py           # Metrics & benchmark API
|   |
|   +-- agent/
|   |   +-- state.py             # Agent state definition (extended phases)
|   |   +-- graph.py             # Agent execution graph with loop detection
|   |   +-- langgraph_executor.py # LangGraph StateGraph builder
|   |   +-- planner.py           # LLM-based planner + replan + agent dispatch
|   |   +-- prompts.py           # Prompt templates (including REPLAN, routing)
|   |   +-- loop_detector.py     # Loop detection engine
|   |   +-- permissions.py       # Tool permission system
|   |   +-- tool_executor.py     # Unified tool execution gateway
|   |   +-- guardrails.py        # Prompt injection sanitization
|   |   +-- sub_agents.py        # Search/Review/Refactor/Validator agents
|   |
|   +-- tools/
|   |   +-- search_code.py       # Code search tool
|   |   +-- read_file.py         # File reading tool
|   |   +-- edit_file.py         # File editing tool
|   |   +-- git_diff.py          # Git diff tool
|   |   +-- run_tests.py         # Test execution tool
|   |   +-- list_files.py        # File listing + dependency analysis
|   |   +-- path_validator.py    # Path traversal & boundary validation
|   |
|   +-- code/
|   |   +-- parser.py            # Python/Java code parser
|   |   +-- indexer.py           # Code chunk indexer
|   |   +-- search.py            # Hybrid search (keyword + BM25)
|   |   +-- dependency_graph.py  # Dependency graph builder & analyzer
|   |
|   +-- sandbox/
|   |   +-- manager.py           # Docker sandbox manager
|   |   +-- docker_runner.py     # Docker execution runner
|   |   +-- policy.py            # Security policy configuration
|   |
|   +-- benchmark/
|   |   +-- cases.py             # 10 benchmark cases
|   |   +-- runner.py            # Benchmark execution engine
|   |   +-- metrics.py           # Metrics collection & aggregation
|   |
|   +-- services/
|   |   +-- task_service.py      # Task lifecycle management
|   |   +-- repository_service.py # Repository operations
|   |   +-- checkpoint_service.py # Agent state checkpoint
|   |   +-- redis_client.py      # Redis client + distributed lock
|   |   +-- git_workflow.py      # Git branch/commit/merge workflow
|   |
|   +-- db/
|   |   +-- models.py            # SQLAlchemy models
|   |   +-- session.py           # Async database session
|   |   +-- enums.py             # Status/type enumerations
|   |
|   +-- observability/
|       +-- logger.py            # Structured logging
|       +-- trace.py             # Distributed tracing
|
+-- tests/
|   +-- test_agent.py            # Agent state machine tests
|   +-- test_sandbox.py          # Sandbox execution tests
|   +-- test_tools.py            # Tool unit tests
|   +-- test_parser.py           # Code parser tests
|   +-- test_api.py              # API integration tests
|   +-- test_git_workflow.py     # Git workflow tests
|   +-- test_benchmark.py        # Benchmark system tests
|   +-- test_dependency_graph.py # Dependency graph tests
|   +-- test_e2e_pipeline.py     # End-to-end pipeline tests
|
+-- sandbox/
|   +-- Dockerfile               # Sandbox container image
|
+-- examples/
|   +-- demo-repository/         # Demo repo with intentional code smells
|
+-- docker-compose.yml
+-- Dockerfile
+-- requirements.txt
+-- .env.example
+-- pytest.ini
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker
- PostgreSQL 16+
- Redis 7+

### 1. Clone and Setup

```bash
git clone https://github.com/Loucy-28/RepoAgent.git
cd RepoAgent

python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your OpenAI API key and database credentials
```

### 3. Start Infrastructure

```bash
docker-compose up -d postgres redis
```

### 4. Build Sandbox Image

```bash
docker build -t repo-agent-sandbox sandbox/
```

### 5. Run the Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Run Tests

```bash
pytest tests/ -v
```

## API Reference

### Tasks

```
POST   /api/v1/tasks                    # Create task (auto-queues agent)
GET    /api/v1/tasks                    # List tasks
GET    /api/v1/tasks/{task_id}          # Get task status
POST   /api/v1/tasks/{task_id}/cancel   # Cancel task
GET    /api/v1/tasks/{task_id}/diff     # Get diff (includes branch info)
```

### Human Review Workflow

```
POST   /api/v1/tasks/{task_id}/approve  # Approve task (WAITING_REVIEW -> APPROVED)
POST   /api/v1/tasks/{task_id}/reject   # Reject task (WAITING_REVIEW -> REJECTED)
POST   /api/v1/tasks/{task_id}/merge    # Merge to main (APPROVED -> MERGED)
```

### Repositories

```
POST   /api/v1/repositories                      # Register repository
GET    /api/v1/repositories                      # List repositories
GET    /api/v1/repositories/{repo_id}             # Get repository
DELETE /api/v1/repositories/{repo_id}             # Delete repository
POST   /api/v1/repositories/{repo_id}/index       # Index code
GET    /api/v1/repositories/{repo_id}/dependencies           # Full dependency graph
GET    /api/v1/repositories/{repo_id}/dependencies/{path}    # Per-file dependencies
```

### Metrics & Benchmark

```
GET    /api/v1/metrics                  # Aggregated metrics summary
GET    /api/v1/metrics/results          # Individual benchmark results
GET    /api/v1/metrics/benchmark-cases  # List all benchmark cases
GET    /api/v1/metrics/categories       # List benchmark categories
POST   /api/v1/metrics/benchmark/run/{case_id}     # Run single benchmark
POST   /api/v1/metrics/benchmark/run-all           # Run all benchmarks
DELETE /api/v1/metrics/results          # Clear metrics
```

## Database Schema

```
repositories
    |
    +---- tasks
    |       |
    |       +---- agent_steps
    |       |
    |       +---- execution_records
    |
    +---- code_chunks
```

### Core Tables

| Table | Purpose |
|-------|---------|
| `repositories` | Registered code repositories |
| `tasks` | Agent task lifecycle (status, iteration, result, branch) |
| `agent_steps` | Individual agent step records (plan, search, edit, test, replan) |
| `code_chunks` | Parsed and indexed code fragments |
| `execution_records` | Sandbox execution audit trail with traces |

## Security Model

### Docker Sandbox Isolation

```bash
docker run \
    --rm \
    --network none \        # No network access
    --memory 256m \         # Memory limit
    --cpus 0.5 \            # CPU limit
    --read-only \           # Read-only root filesystem
    --tmpfs /tmp:size=64m \ # Temporary writable space
    repo-agent-sandbox
```

### Tool Permission System

All tool calls are routed through a unified `ToolExecutor` gateway. The pipeline is: permission check (`ToolPermissionChecker`) → handler lookup → async execution → audit logging. No agent can bypass this gateway to perform file writes, code execution, or any other side-effecting operation.

### Repository Boundary Enforcement

All file write operations (`edit_file`) pass `repo_path` as `allowed_root` through the tool chain:

```
Agent → ToolExecutor → edit_file(allowed_root=repo_path) → validate_path()
```

`validate_path()` enforces a whitelist check: the resolved absolute path must start with the repository root. This is supplemented by a blacklist blocking system directories (`/etc/`, `/proc/`, `C:\Windows`, etc.) and path traversal detection (`..` segments).

## Benchmark System

10 predefined benchmark cases across 8 categories:

| ID | Name | Category | Difficulty |
|----|------|----------|------------|
| bench-001 | fix_off_by_one | bug_fix | easy |
| bench-002 | add_missing_function | feature_add | easy |
| bench-003 | rename_variable_refactor | refactor | easy |
| bench-004 | detect_sql_injection | security | medium |
| bench-005 | add_error_handling | robustness | medium |
| bench-006 | add_docstrings | documentation | easy |
| bench-007 | extract_method | refactor | medium |
| bench-008 | add_type_hints | type_safety | medium |
| bench-009 | fix_race_condition | concurrency | hard |
| bench-010 | add_unit_test | testing | medium |

Metrics collected per run: success rate, duration, iterations, loop detection rate, test pass rate, replan count, grouped by category and difficulty.

## Observability

Every agent task produces a complete trace:

```
Task: review order module
  |
  +-- Planning       830ms   SUCCESS
  |
  +-- Search         120ms   SUCCESS  (5 results)
  |
  +-- Review        1520ms   SUCCESS  (3 findings)
  |
  +-- Edit           310ms   SUCCESS  (2 edits, committed to agent/task-abc123)
  |
  +-- Test          1842ms   FAILED   (assertion error)
  |
  +-- Repair         920ms   SUCCESS
  |
  +-- Test          1730ms   SUCCESS
  |
  +-- WAITING_REVIEW
```

## Demo

The `examples/demo-repository/` contains a sample project with intentional code issues:

- `order/service.py` -- Long Method, Potential Bug (KeyError), Poor Responsibility
- `order/controller.py` -- Poor Responsibility (mixed concerns)
- `user/service.py` -- Duplicate Code patterns

Run the agent against it:

```bash
# 1. Register the demo repository
curl -X POST http://localhost:8000/api/v1/repositories \
  -H "Content-Type: application/json" \
  -d '{"name": "demo", "path": "./examples/demo-repository", "language": "python"}'

# 2. Index the code
curl -X POST http://localhost:8000/api/v1/repositories/{repo_id}/index

# 3. Create a review task
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"repository_id": "{repo_id}", "description": "Review the order module for code smells and fix them"}'

# 4. Check task status
curl http://localhost:8000/api/v1/tasks/{task_id}

# 5. Get the diff (includes branch info)
curl http://localhost:8000/api/v1/tasks/{task_id}/diff

# 6. Approve and merge
curl -X POST http://localhost:8000/api/v1/tasks/{task_id}/approve
curl -X POST http://localhost:8000/api/v1/tasks/{task_id}/merge
```

## Test Coverage

| Test File | Coverage | Cases |
|-----------|----------|-------|
| `test_parser.py` | Python/Java code parser | 10 |
| `test_sandbox.py` | Sandbox execution (normal/error/timeout) | 9 |
| `test_agent.py` | Agent state machine & transitions | 5 |
| `test_tools.py` | Tool layer (read/write/search/deps) | 12 |
| `test_api.py` | API integration tests | 5 |
| `test_git_workflow.py` | Git branch/commit/merge workflow | 5 |
| `test_benchmark.py` | Benchmark system & metrics API | 12 |
| `test_dependency_graph.py` | Dependency graph build & analysis | 10 |
| `test_e2e_pipeline.py` | End-to-end pipeline (plan→test→repair→merge) | 9 |

## License

MIT

# RepoAgent

**Enterprise Coding Agent for Code Review and Automated Refactoring**

> An AI-powered coding agent that understands codebases, identifies code issues, proposes refactoring plans, modifies code automatically, and validates changes in an isolated Docker sandbox with test-driven repair loops.

## Architecture

```
                    RepoAgent
                       |
        +--------------+--------------+
        |              |              |
        v              v              v
   Agent Layer    Code Intelligence  Runtime
        |              |              |
        v              v              v
   LangGraph       Code Search       Docker
   Planning        Parser            Sandbox
   Tool Calling    Index             Test
   State Machine   Dependency        Resource Limit
        |              |              |
        +--------------+--------------+
                       |
                       v
                 Backend Layer
                       |
              +--------+--------+
              v        v        v
           FastAPI   Redis   PostgreSQL
              |
              v
        Observability
              |
              v
          Trace / Log
```

## Core Workflow

```
User submits task
      |
      v
 Agent Planner  -->  Understand task
      |
      v
 Code Repository  -->  Code Search / Analysis
      |
      v
 Code Review  -->  Find issues
      |
      v
 Edit Code  -->  Git Diff
      |
      v
 Docker Sandbox  -->  Compile / Test
      |
   +--+--+
   |     |
 FAIL   PASS
   |     |
   v     v
Repair  Done
   |     |
   +--+--+
      |
      v
  Final Diff  -->  Human Review
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
                                                    COMPLETED   REPAIRING -> TESTING
                                                                              
Max iterations exceeded -> FAILED
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI, Pydantic |
| Database | PostgreSQL, SQLAlchemy (async) |
| Cache/Lock | Redis |
| Agent | LangGraph, LangChain, OpenAI |
| Code Analysis | AST Parser (Python), Regex Parser (Java) |
| Sandbox | Docker (resource-limited, network-isolated) |
| Observability | Structured Logging (structlog), Distributed Tracing |
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
|   |   +-- tasks.py             # Task CRUD + agent execution
|   |   +-- repositories.py      # Repository management + indexing
|   |
|   +-- agent/
|   |   +-- state.py             # Agent state definition
|   |   +-- graph.py             # Agent execution graph (state machine)
|   |   +-- planner.py           # LLM-based planner
|   |   +-- prompts.py           # Prompt templates
|   |
|   +-- tools/
|   |   +-- search_code.py       # Code search tool
|   |   +-- read_file.py         # File reading tool
|   |   +-- edit_file.py         # File editing tool
|   |   +-- git_diff.py          # Git diff tool
|   |   +-- run_tests.py         # Test execution tool
|   |   +-- list_files.py        # File listing + dependency analysis
|   |
|   +-- code/
|   |   +-- parser.py            # Python/Java code parser
|   |   +-- indexer.py           # Code chunk indexer
|   |   +-- search.py            # Hybrid search (keyword + BM25)
|   |
|   +-- sandbox/
|   |   +-- manager.py           # Docker sandbox manager
|   |   +-- docker_runner.py     # Docker execution runner
|   |   +-- policy.py            # Security policy configuration
|   |
|   +-- services/
|   |   +-- task_service.py      # Task lifecycle management
|   |   +-- repository_service.py # Repository operations
|   |   +-- checkpoint_service.py # Agent state checkpoint
|   |   +-- redis_client.py      # Redis client + distributed lock
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
|
+-- sandbox/
|   +-- Dockerfile               # Sandbox container image
|
+-- examples/
|   +-- demo-repository/         # Demo repo with intentional code smells
|       +-- order/
|       |   +-- service.py       # Long Method, Potential Bug, Poor Responsibility
|       |   +-- repository.py    # Data access layer
|       |   +-- controller.py    # Poor Responsibility
|       +-- user/
|       |   +-- service.py       # Duplicate Code
|       +-- tests/
|           +-- test_order.py    # Test suite
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
git clone https://github.com/your-username/repo-agent.git
cd repo-agent

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

### Health Check

```
GET /health
```

Response:
```json
{
  "status": "healthy",
  "service": "repo-agent",
  "version": "1.0.0"
}
```

### Register Repository

```
POST /api/v1/repositories
Content-Type: application/json

{
  "name": "my-project",
  "path": "/path/to/project",
  "language": "python"
}
```

### Index Repository

```
POST /api/v1/repositories/{repo_id}/index
```

Response:
```json
{
  "repository_id": "uuid",
  "chunks_indexed": 42,
  "status": "completed"
}
```

### Create Agent Task

```
POST /api/v1/tasks
Content-Type: application/json

{
  "repository_id": "uuid",
  "description": "Review the order module for code smells and fix them",
  "max_iterations": 5
}
```

Response:
```json
{
  "id": "task-uuid",
  "status": "CREATED",
  "current_step": "",
  "iteration": 0,
  "max_iterations": 5
}
```

### Get Task Status

```
GET /api/v1/tasks/{task_id}
```

### Get Task Diff

```
GET /api/v1/tasks/{task_id}/diff
```

### Cancel Task

```
POST /api/v1/tasks/{task_id}/cancel
```

### List Tasks

```
GET /api/v1/tasks?repository_id={repo_id}&limit=50
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
| `tasks` | Agent task lifecycle (status, iteration, result) |
| `agent_steps` | Individual agent step records (plan, search, edit, test) |
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

| Control | Purpose |
|---------|---------|
| Network disabled | Prevents data exfiltration and external access |
| Memory limit | Prevents OOM attacks on host |
| CPU limit | Prevents resource exhaustion |
| Read-only root FS | Prevents filesystem modification |
| Timeout | Prevents infinite loops and fork bombs |
| Temporary workspace | Isolated per-execution directory |

> This design reduces the impact of untrusted code on the host system and other tasks, controlling resource consumption and attack surface.

## Code Review Capabilities

The agent detects 4 categories of code smells:

| Category | Description | Example |
|----------|-------------|---------|
| Long Method | Function too long, hard to understand | 100+ line function |
| Duplicate Code | Repeated logic across files | Same validation in multiple places |
| Poor Responsibility | Class/function doing too many things | Controller with business logic |
| Potential Bug | Missing checks, unsafe operations | KeyError from unchecked dict access |

## Agent Tool Interface

The agent interacts with the system through controlled tools, never directly:

| Tool | Description |
|------|-------------|
| `search_code` | Search repository for relevant code |
| `read_file` | Read file contents with line range |
| `list_files` | List repository files by extension |
| `get_dependencies` | Analyze file imports/dependencies |
| `edit_file` | Modify file contents |
| `git_diff` | Generate diff of changes |
| `run_tests` | Execute tests in sandbox |

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
  +-- Edit           310ms   SUCCESS  (2 edits)
  |
  +-- Test          1842ms   FAILED   (assertion error)
  |
  +-- Repair         920ms   SUCCESS
  |
  +-- Test          1730ms   SUCCESS
  |
  +-- COMPLETED
```

## Demo

The `examples/demo-repository/` contains a sample project with intentional code issues:

- `order/service.py` — Long Method, Potential Bug (KeyError), Poor Responsibility
- `order/controller.py` — Poor Responsibility (mixed concerns)
- `user/service.py` — Duplicate Code patterns

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

# 5. Get the diff
curl http://localhost:8000/api/v1/tasks/{task_id}/diff
```

## Design Decisions

### Why PostgreSQL + Redis?

| Concern | PostgreSQL | Redis |
|---------|-----------|-------|
| Task state | Persistent storage | - |
| Agent steps | Audit trail | - |
| Code chunks | Indexed search | - |
| Execution records | Trace persistence | - |
| Distributed lock | - | Prevent concurrent execution |
| Agent temp state | - | Fast read/write, TTL |
| Task dedup | - | Short-lived keys |

### Why Tool-based Agent?

The agent never directly executes system operations. All capabilities are exposed through controlled tool interfaces with defined schemas. This provides:

- **Auditability**: Every tool call is logged
- **Safety**: Tools enforce boundaries (path validation, timeout)
- **Testability**: Tools can be unit tested independently
- **Extensibility**: New capabilities added as new tools

### Why Docker Sandbox?

Code execution in a coding agent is inherently risky. Docker provides:

- **Process isolation**: Container boundary
- **Resource limits**: CPU, memory caps
- **Network control**: Disable external access
- **Filesystem protection**: Read-only root FS
- **Ephemeral execution**: Clean state per run

## License

MIT

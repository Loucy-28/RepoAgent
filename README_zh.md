# RepoAgent v2.0

**企业级 Coding Agent —— 代码审查与自动化重构平台**

> 一个面向企业代码库的 AI 多 Agent 编码平台，能够理解代码库、检索相关代码、发现代码问题、制定重构计划、自动修改代码，并在隔离沙箱中编译和测试，根据测试结果自动修复，最终生成可人工审核的 Git Diff。支持循环检测与自动重规划、依赖图分析、人工审核工作流、Git 分支管理以及内置基准测试系统。

## v2.0 新特性

| 特性 | 说明 |
|------|------|
| 循环检测与自动重规划 | 检测 Agent 循环（同一工具调用 >= 3 次、同一错误重复 >= 2 次），触发智能重规划 |
| 多 Agent 架构 | 编排器将任务分派给搜索、审查、重构、验证四个专业 Agent，工具权限隔离 |
| 依赖图 | 基于 AST 的代码依赖分析，支持影响分析和调用链追踪 |
| 人工审核工作流 | 任务状态机扩展：WAITING_REVIEW -> APPROVED -> MERGED 流程 |
| Git 分支工作流 | 每个任务创建独立分支（`agent/task-{id}`），提交变更，支持合并到主分支 |
| 基准测试系统 | 8 个类别共 10 个预定义基准用例，支持指标采集和 API 查询 |

## 系统架构

```
                       RepoAgent v2.0
                            |
            +---------------+---------------+
            |               |               |
            v               v               v
       多 Agent 层      代码智能层         运行时层
            |               |               |
   +--------+--------+     v               v
   |   |    |    |   |  依赖图            Docker
   v   v    v    v   v  构建              沙箱执行
 搜索 审查  重构  验证                    测试验证
            |               |               |
            +-------+-------+-------+-------+
                    |               |
                    v               v
              循环检测          Git 工作流
              自动重规划        分支 / 合并
                    |               |
                    +-------+-------+
                            |
                            v
                       后端服务层
                            |
                   +--------+--------+
                   v        v        v
                FastAPI   Redis   PostgreSQL
                   |
                   v
            可观测性 + 基准测试
```

## 核心工作流

```
用户提交任务
      |
      v
 创建分支 (agent/task-{id})  ──失败──>  FAILED
      |
      v (成功)
 Agent 规划器  -->  理解任务 + LLM Agent 调度
      |
      v
 代码搜索 (SearchAgent)  -->  检索相关代码
      |
      v
 代码审查 (ReviewAgent)  -->  发现问题 + 依赖上下文
      |                            (可通过 LLM 路由跳过)
      v
 修改代码 (RefactorAgent)  -->  生成修复 (通过 ToolExecutor)
      |
      v
 Docker 沙箱 (ValidatorAgent)  -->  编译 / 测试
      |
   +--+--+
   |     |
 失败   通过
   |     |
   v     v
 迭代 < 上限?   提交变更到分支
  ├─是─> 自动修复    |
  └─否─> FAILED     |
   |                 |
   +-----------------+
      |
      v
 WAITING_REVIEW  -->  人工审核
      |
   +--+--+
   |     |
 通过   拒绝
   |
   v
 合并到 main
```

## Agent 状态机

```
CREATED -> PLANNING -> SEARCHING -> ANALYZING -> EDITING -> TESTING
                                                              |
                                                        +-----+-----+
                                                        |           |
                                                      通过         失败
                                                        |           |
                                                        v           v
                                                    COMPLETED   迭代 < 上限?
                                                                   |       |
                                                                  是      否
                                                                   |       |
                                                                   v       v
                                                               REPAIRING  FAILED
                                                                   |
                                                                   v
                                                                TESTING
                                                                (重试)

检测到循环? -> REPLANNING (最多 2 次重规划) -> SEARCHING (重试)
COMPLETED -> WAITING_REVIEW -> APPROVED -> MERGED
                            -> REJECTED
```

| 状态 | 说明 |
|------|------|
| `CREATED` | 任务已创建，等待执行 |
| `PLANNING` | Agent 正在理解任务并制定执行计划 |
| `SEARCHING` | 在代码仓库中检索相关代码 |
| `ANALYZING` | 对检索到的代码进行审查分析（含依赖上下文） |
| `EDITING` | 根据分析结果修改代码 |
| `TESTING` | 在 Docker 沙箱中运行测试 |
| `REPAIRING` | 测试失败，Agent 分析错误并修复代码 |
| `REPLANNING` | 检测到循环，Agent 生成完全不同的新计划 |
| `WAITING_REVIEW` | 任务完成，等待人工审核 |
| `APPROVED` | 审核者通过了变更 |
| `REJECTED` | 审核者拒绝了变更 |
| `MERGED` | 变更已合并到主分支 |
| `COMPLETED` | 测试通过，任务完成 |
| `FAILED` | 超过最大迭代次数或发生不可恢复的错误 |

## 多 Agent 架构

规划完成后，编排器通过 LLM 路由决策动态选择需要调用的专业 Agent。例如，简单的文档任务可能跳过 ReviewAgent，而复杂的重构任务则调用全部 Agent。所有工具调用都通过统一的 `ToolExecutor` 权限网关路由。

| Agent | 角色 | 可用工具 |
|-------|------|----------|
| **Orchestrator** | 规划、路由与协调 | `create_plan`, `replan` |
| **SearchAgent** | 代码检索与依赖上下文 | `search_code`, `read_file`, `list_files`, `get_dependencies` |
| **ReviewAgent** | 代码审查与分析（LLM 选择） | `search_code`, `read_file`, `get_dependencies`, `review_code` |
| **RefactorAgent** | 代码修改 | `read_file`, `edit_file`, `git_diff` |
| **ValidatorAgent** | 测试执行（LLM 选择） | `run_tests`, `read_file` |

### 循环检测

系统监控 Agent 行为，检测三种循环模式：

| 模式 | 阈值 | 动作 |
|------|------|------|
| 同一工具反复调用 | 连续 >= 3 次 | 触发重规划 |
| 同一错误重复出现 | >= 2 次 | 触发重规划 |
| 修复后测试仍失败 | >= 3 次 | 触发重规划 |

检测到循环且 `replan_count < max_replans` 时，Agent 会：
1. 构建失败摘要，说明哪里出了问题
2. 通过 LLM 生成完全不同的新计划
3. 清除审查结果，从搜索阶段重新开始

## 依赖图

代码智能层在索引时构建完整的依赖图：

```python
# 为仓库构建依赖图
dependency_graph.build(repo_path)

# 获取文件的依赖关系
deps = dependency_graph.get_dependencies("/path/to/file.py")
# -> {"imports": [...], "imported_by": [...], "calls": [...], "called_by": [...]}

# 影响分析：这个文件变更会影响什么？
impact = dependency_graph.get_impact_analysis("/path/to/file.py")
# -> {"direct": [...], "transitive": [...]}
```

## 技术栈

| 层级 | 技术 |
|------|------|
| API 服务 | FastAPI, Pydantic |
| 数据库 | PostgreSQL, SQLAlchemy (异步) |
| 缓存/锁 | Redis |
| Agent 引擎 | LangGraph, LangChain, OpenAI |
| 代码分析 | AST 解析器 (Python), 正则解析器 (Java) |
| 依赖图 | 基于 AST (Python), 基于正则 (Java) |
| 安全沙箱 | Docker (资源限制、网络隔离) |
| Git 工作流 | subprocess (分支、提交、合并) |
| 可观测性 | 结构化日志 (structlog)、分布式链路追踪 |
| 基准测试 | 内置运行器 + 指标采集 |
| 测试框架 | pytest, pytest-asyncio |

## 项目结构

```
repo-agent/
|
+-- app/
|   +-- main.py                  # FastAPI 应用入口
|   +-- config.py                # Pydantic 配置管理
|   |
|   +-- api/
|   |   +-- health.py            # 健康检查接口
|   |   +-- tasks.py             # 任务 CRUD + Agent 执行 + 审核工作流
|   |   +-- repositories.py      # 仓库管理 + 代码索引 + 依赖查询
|   |   +-- metrics.py           # 指标与基准测试接口
|   |
|   +-- agent/
|   |   +-- state.py             # Agent 状态定义（扩展阶段）
|   |   +-- graph.py             # Agent 执行图（含循环检测）
|   |   +-- langgraph_executor.py # LangGraph StateGraph 构建器
|   |   +-- planner.py           # 基于 LLM 的规划器 + 重规划 + Agent 调度
|   |   +-- prompts.py           # 提示词模板（含 REPLAN、路由）
|   |   +-- loop_detector.py     # 循环检测引擎
|   |   +-- permissions.py       # 工具权限系统
|   |   +-- tool_executor.py     # 统一工具执行网关
|   |   +-- guardrails.py        # Prompt 注入防护
|   |   +-- sub_agents.py        # 搜索/审查/重构/验证 Agent
|   |
|   +-- tools/
|   |   +-- search_code.py       # 代码搜索工具
|   |   +-- read_file.py         # 文件读取工具
|   |   +-- edit_file.py         # 文件编辑工具
|   |   +-- git_diff.py          # Git Diff 工具
|   |   +-- run_tests.py         # 测试执行工具
|   |   +-- list_files.py        # 文件列表 + 依赖分析
|   |   +-- path_validator.py    # 路径穿越与边界校验
|   |
|   +-- code/
|   |   +-- parser.py            # Python/Java 代码解析器
|   |   +-- indexer.py           # 代码块索引器
|   |   +-- search.py            # 混合搜索（关键词 + BM25）
|   |   +-- dependency_graph.py  # 依赖图构建与分析
|   |
|   +-- sandbox/
|   |   +-- manager.py           # Docker 沙箱管理器
|   |   +-- docker_runner.py     # Docker 执行器
|   |   +-- policy.py            # 安全策略配置
|   |
|   +-- benchmark/
|   |   +-- cases.py             # 10 个基准测试用例
|   |   +-- runner.py            # 基准测试执行引擎
|   |   +-- metrics.py           # 指标采集与聚合
|   |
|   +-- services/
|   |   +-- task_service.py      # 任务生命周期管理
|   |   +-- repository_service.py # 仓库操作服务
|   |   +-- checkpoint_service.py # Agent 状态检查点
|   |   +-- redis_client.py      # Redis 客户端 + 分布式锁
|   |   +-- git_workflow.py      # Git 分支/提交/合并工作流
|   |
|   +-- db/
|   |   +-- models.py            # SQLAlchemy 数据模型
|   |   +-- session.py           # 异步数据库会话
|   |   +-- enums.py             # 状态/类型枚举
|   |
|   +-- observability/
|       +-- logger.py            # 结构化日志
|       +-- trace.py             # 分布式链路追踪
|
+-- tests/
|   +-- test_agent.py            # Agent 状态机测试
|   +-- test_sandbox.py          # 沙箱执行测试
|   +-- test_tools.py            # 工具单元测试
|   +-- test_parser.py           # 代码解析器测试
|   +-- test_api.py              # API 集成测试
|   +-- test_git_workflow.py     # Git 工作流测试
|   +-- test_benchmark.py        # 基准测试系统测试
|   +-- test_dependency_graph.py # 依赖图测试
|   +-- test_e2e_pipeline.py     # 端到端流水线测试
|
+-- sandbox/
|   +-- Dockerfile               # 沙箱容器镜像
|
+-- examples/
|   +-- demo-repository/         # 含故意植入代码异味的演示仓库
|
+-- docker-compose.yml
+-- Dockerfile
+-- requirements.txt
+-- .env.example
+-- pytest.ini
```

## 快速开始

### 环境要求

- Python 3.11+
- Docker
- PostgreSQL 16+
- Redis 7+

### 1. 克隆并安装

```bash
git clone https://github.com/your-username/repo-agent.git
cd repo-agent

python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 OpenAI API Key 和数据库连接信息
```

### 3. 启动基础设施

```bash
docker-compose up -d postgres redis
```

### 4. 构建沙箱镜像

```bash
docker build -t repo-agent-sandbox sandbox/
```

### 5. 启动应用

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. 运行测试

```bash
pytest tests/ -v
```

## API 接口文档

### 任务管理

```
POST   /api/v1/tasks                    # 创建任务（自动排队执行）
GET    /api/v1/tasks                    # 任务列表
GET    /api/v1/tasks/{task_id}          # 查询任务状态
POST   /api/v1/tasks/{task_id}/cancel   # 取消任务
GET    /api/v1/tasks/{task_id}/diff     # 获取 Diff（含分支信息）
```

### 人工审核工作流

```
POST   /api/v1/tasks/{task_id}/approve  # 通过任务（WAITING_REVIEW -> APPROVED）
POST   /api/v1/tasks/{task_id}/reject   # 拒绝任务（WAITING_REVIEW -> REJECTED）
POST   /api/v1/tasks/{task_id}/merge    # 合并到主分支（APPROVED -> MERGED）
```

### 仓库管理

```
POST   /api/v1/repositories                      # 注册仓库
GET    /api/v1/repositories                      # 仓库列表
GET    /api/v1/repositories/{repo_id}             # 查询仓库
DELETE /api/v1/repositories/{repo_id}             # 删除仓库
POST   /api/v1/repositories/{repo_id}/index       # 建立代码索引
GET    /api/v1/repositories/{repo_id}/dependencies           # 完整依赖图
GET    /api/v1/repositories/{repo_id}/dependencies/{path}    # 单文件依赖
```

### 指标与基准测试

```
GET    /api/v1/metrics                  # 聚合指标摘要
GET    /api/v1/metrics/results          # 单次基准测试结果
GET    /api/v1/metrics/benchmark-cases  # 所有基准测试用例
GET    /api/v1/metrics/categories       # 基准测试类别
POST   /api/v1/metrics/benchmark/run/{case_id}     # 运行单个基准测试
POST   /api/v1/metrics/benchmark/run-all           # 运行全部基准测试
DELETE /api/v1/metrics/results          # 清除指标
```

## 数据库设计

```
repositories（代码仓库）
    |
    +---- tasks（任务）
    |       |
    |       +---- agent_steps（Agent 步骤）
    |       |
    |       +---- execution_records（执行记录）
    |
    +---- code_chunks（代码块）
```

### 核心表说明

| 表名 | 用途 |
|------|------|
| `repositories` | 已注册的代码仓库信息 |
| `tasks` | Agent 任务生命周期（状态、迭代次数、结果、分支） |
| `agent_steps` | Agent 每一步的执行记录（规划、搜索、编辑、测试、重规划） |
| `code_chunks` | 解析并索引的代码片段 |
| `execution_records` | 沙箱执行审计记录，含链路追踪信息 |

### PostgreSQL 与 Redis 的分工

| 关注点 | PostgreSQL | Redis |
|--------|-----------|-------|
| 任务状态 | 持久化存储 | - |
| Agent 步骤 | 审计追踪 | - |
| 代码块 | 索引检索 | - |
| 执行记录 | 追踪持久化 | - |
| 分布式锁 | - | 防止并发执行 |
| Agent 临时状态 | - | 高速读写，支持 TTL |
| 任务去重 | - | 短生命周期 Key |

## 安全模型

### Docker 沙箱隔离

```bash
docker run \
    --rm \
    --network none \        # 禁用网络访问
    --memory 256m \         # 内存限制
    --cpus 0.5 \            # CPU 限制
    --read-only \           # 只读根文件系统
    --tmpfs /tmp:size=64m \ # 临时可写空间
    repo-agent-sandbox
```

### 工具权限系统

所有工具调用都通过统一的 `ToolExecutor` 网关路由。执行管线为：权限检查（`ToolPermissionChecker`）→ Handler 查找 → 异步执行 → 审计日志。任何 Agent 都无法绕过此网关执行文件写入、代码运行或其他有副作用的操作。

### 仓库边界强制

所有文件写入操作（`edit_file`）在工具链中传递 `repo_path` 作为 `allowed_root`：

```
Agent → ToolExecutor → edit_file(allowed_root=repo_path) → validate_path()
```

`validate_path()` 执行白名单检查：解析后的绝对路径必须以仓库根目录开头。同时辅以黑名单阻止系统目录（`/etc/`、`/proc/`、`C:\Windows` 等）和路径穿越检测（`..` 段）。

## 基准测试系统

10 个预定义基准测试用例，覆盖 8 个类别：

| ID | 名称 | 类别 | 难度 |
|----|------|------|------|
| bench-001 | fix_off_by_one | bug_fix | 简单 |
| bench-002 | add_missing_function | feature_add | 简单 |
| bench-003 | rename_variable_refactor | refactor | 简单 |
| bench-004 | detect_sql_injection | security | 中等 |
| bench-005 | add_error_handling | robustness | 中等 |
| bench-006 | add_docstrings | documentation | 简单 |
| bench-007 | extract_method | refactor | 中等 |
| bench-008 | add_type_hints | type_safety | 中等 |
| bench-009 | fix_race_condition | concurrency | 困难 |
| bench-010 | add_unit_test | testing | 中等 |

每次运行采集的指标：成功率、耗时、迭代次数、循环检测率、测试通过率、重规划次数，按类别和难度分组统计。

## 可观测性

每个 Agent 任务都会生成完整的执行追踪：

```
任务：审查订单模块
  |
  +-- 规划 (Planning)       830ms   成功
  |
  +-- 搜索 (Search)         120ms   成功   (5 条结果)
  |
  +-- 审查 (Review)        1520ms   成功   (3 个发现)
  |
  +-- 编辑 (Edit)           310ms   成功   (2 处修改, 已提交到 agent/task-abc123)
  |
  +-- 测试 (Test)          1842ms   失败   (断言错误)
  |
  +-- 修复 (Repair)         920ms   成功
  |
  +-- 测试 (Test)          1730ms   成功
  |
  +-- WAITING_REVIEW
```

## 演示

`examples/demo-repository/` 目录包含一个故意植入代码问题的示例项目：

- `order/service.py` — 过长方法、潜在 Bug (KeyError)、职责混乱
- `order/controller.py` — 职责混乱（混合了校验、业务逻辑和响应格式化）
- `user/service.py` — 重复代码模式

运行 Agent 进行审查：

```bash
# 1. 注册演示仓库
curl -X POST http://localhost:8000/api/v1/repositories \
  -H "Content-Type: application/json" \
  -d '{"name": "demo", "path": "./examples/demo-repository", "language": "python"}'

# 2. 建立代码索引
curl -X POST http://localhost:8000/api/v1/repositories/{repo_id}/index

# 3. 创建审查任务
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"repository_id": "{repo_id}", "description": "检查订单模块的代码异味并自动修复"}'

# 4. 查看任务状态
curl http://localhost:8000/api/v1/tasks/{task_id}

# 5. 获取代码 Diff（含分支信息）
curl http://localhost:8000/api/v1/tasks/{task_id}/diff

# 6. 审核通过并合并
curl -X POST http://localhost:8000/api/v1/tasks/{task_id}/approve
curl -X POST http://localhost:8000/api/v1/tasks/{task_id}/merge
```

## 测试覆盖

| 测试文件 | 测试内容 | 用例数 |
|----------|----------|--------|
| `test_parser.py` | Python/Java 代码解析器 | 10 |
| `test_sandbox.py` | 沙箱执行（正常/错误/超时） | 9 |
| `test_agent.py` | Agent 状态机与状态转换 | 5 |
| `test_tools.py` | 工具层（读写/搜索/依赖） | 12 |
| `test_api.py` | API 集成测试 | 5 |
| `test_git_workflow.py` | Git 分支/提交/合并工作流 | 5 |
| `test_benchmark.py` | 基准测试系统与指标 API | 12 |
| `test_dependency_graph.py` | 依赖图构建与分析 | 10 |
| `test_e2e_pipeline.py` | 端到端流水线（规划→测试→修复→合并） | 9 |

## 许可证

MIT

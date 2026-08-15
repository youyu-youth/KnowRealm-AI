# 规范：LangChain 1.x + LangGraph（AI 编排层）

> 适用范围：`services/api/app/agents/`（Summary / Tutor / TeachBack / Autopilot / MisconceptionVerification 五个 Graph，功能基线红线 #2）及一切 LLM 调用、RAG 检索代码。

## 0. 版本基线（2026-08 核实）

| 包 | 基线 | 说明 |
|---|---|---|
| `langchain` / `langchain-core` | **1.3.x**（当前 1.3.15） | 稳定线 |
| `langgraph` | **1.2.x**（当前 1.2.11） | ⚠️ **LangGraph 没有 1.3 版本**，版本线与 LangChain 相互独立，官方协调发布的兼容组合就是 langchain 1.3.x + langgraph 1.2.x |
| `langgraph-checkpoint-postgres` | 最新稳定 | 跟随 langgraph 版本线 |
| `langchain-openai` / `langchain-community` | 1.x / 最新 | 配套 langchain-core 1.3.x |
| ~~langchain-postgres~~ | — | **不采用**：向量存储用自建 `semantic_embeddings` 表（数据模型 §4.6，统一向量生命周期），其 PGVector collection 自建表与该设计冲突 |

- 依赖统一用 **uv** 锁定（`uv.lock`），禁止手动改版本绕过锁文件。
- 升级原则：小版本跟进，**不追 pre-release（如 1.4.0a1）**。

## 1. 包结构：只用拆分包，不用 monolithic 旧用法

只允许 import 以下包：

```
langchain              # 仅 create_agent / middleware
langchain-core         # 消息、Runnable、@tool、Document
langchain-openai       # ChatOpenAI / OpenAIEmbeddings（指向 DashScope）
langchain-community    # 文档 Loader
langgraph              # StateGraph / interrupt / Command / checkpointer
# 注意：不用 langchain-postgres（向量检索走自建 semantic_embeddings 表，见 §10）
```

```python
# ✅ 正确：从拆分包导入
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# ❌ 错误：0.x 时代的旧命名空间，1.x 中已移除或不维护
from langchain.chains import RetrievalQA
from langchain.agents import AgentExecutor, create_react_agent
```

## 2. 模型接入：统一工厂，DashScope 走 OpenAI 兼容端点

模型实例只在一个工厂模块创建（如 `agents/llm.py`），密钥来自 `pydantic-settings`，禁止散落硬编码。

```python
# agents/llm.py
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from app.core.config import settings

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

def get_llm(temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        model="qwen-plus",
        base_url=DASHSCOPE_BASE_URL,
        api_key=settings.dashscope_api_key,
        temperature=temperature,
    )

def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model="text-embedding-v3",
        base_url=DASHSCOPE_BASE_URL,
        api_key=settings.dashscope_api_key,
        dimensions=1024,                    # 必须与 pgvector 列 vector(1024) 一致
        check_embedding_ctx_length=False,   # DashScope 兼容端点不支持 tiktoken 预分片，必须关
    )
```

> `check_embedding_ctx_length=False` 是 DashScope 兼容模式的已知兼容性要求，漏掉会报错或产生错误分片。

## 3. Agent：只用 `create_agent()`（1.x 唯一标准）

需要"LLM 自主调用工具"的循环时用 `create_agent`；固定流程用 StateGraph（见 §5）。旧式 `AgentExecutor` 一律禁止。

```python
from langchain.agents import create_agent
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

@tool
def search_course_material(query: str, course_id: str) -> str:
    """在课程资料中检索与问题相关的片段。

    Args:
        query: 检索问题，2~10 个词。
        course_id: 课程 ID。
    """
    ...

agent = create_agent(
    model=get_llm(),
    tools=[search_course_material],
    system_prompt="你是课堂学习助手，回答须基于检索到的课程内容。",
    checkpointer=InMemorySaver(),  # 生产换 PostgresSaver，见 §7
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "什么是 MVCC？"}]},
    config={"configurable": {"thread_id": "chat-123"}, "recursion_limit": 10},
)
print(result["messages"][-1].content)  # ✅ 从 messages 取结果，不是 result.content
```

规则：
- 工具的 docstring 必须写清楚**做什么、什么时候用**，这是 LLM 选择工具的唯一依据。
- 生产代码必须传 `checkpointer` + `thread_id`，否则跨请求失忆。
- 必须设置 `recursion_limit`，防止死循环。

## 4. 结构化输出：`with_structured_output` + Pydantic v2

习题、知识点、Concept 等 AI 产物必须走结构化输出，Schema 放 `schemas/` 目录。

```python
from pydantic import BaseModel, Field

class KnowledgePoint(BaseModel):
    title: str = Field(description="知识点名称，不超过 30 字")
    content: str = Field(description="知识点内容摘要")
    difficulty: int = Field(ge=1, le=5, description="难度 1-5")

structured_llm = get_llm().with_structured_output(KnowledgePoint)
kp = structured_llm.invoke("从以下转写文本中抽取知识点：\n" + transcript)
# kp 已是 KnowledgePoint 实例，类型安全，可直接入库
```

规则：Schema 字段必须带 `description` 和必要的约束（`ge/le/max_length`），让校验挡在入库之前。

## 5. LangGraph StateGraph：固定管线用图

Summary/Tutor/TeachBack/Autopilot/MisconceptionVerification 五个 Graph 各自独立文件，**通过 Learning Event 与 Profile 共享状态，禁止合并成超级 Graph**（架构约束 §29）。

**什么才进 Graph（负面清单，功能基线红线 #2）**：只有需要状态、暂停恢复、HITL 或 Agent 决策的流程才用 LangGraph；普通 CRUD 与确定性业务逻辑（Course/Quiz/Todo/EvidenceBuilder/MasteryEngine/QuestionSelector 等）写成普通确定性 Python Service，**不进 Graph**。

**Agent/节点写入红线**：Graph 节点禁止直写 `user_concept_mastery` 等 mastery 类表（唯一写入口是 Mastery Engine，红线 #3）——节点只发 Learning Event；AI 产物（确认结果、版本链）必须落业务表，**Checkpoint 只存运行态、不是业务事实**。

### 5.1 状态定义与 reducer

```python
from typing import Annotated
from typing_extensions import TypedDict
import operator

class SummaryState(TypedDict):
    transcript: str
    summary: str                                    # 默认覆盖语义
    messages: Annotated[list, operator.add]         # 列表字段必须加 reducer！
```

```python
# ❌ 没加 reducer：节点2 返回的列表会整个覆盖节点1 的结果
class Bad(TypedDict):
    items: list

# ✅ 加了 operator.add：追加合并
class Good(TypedDict):
    items: Annotated[list, operator.add]
```

### 5.2 节点：返回部分更新，不修改原状态

```python
def generate_summary(state: SummaryState) -> dict:
    llm = get_llm()
    result = llm.invoke(f"总结以下课堂转写：{state['transcript']}")
    return {"summary": result.content}   # ✅ 只返回要更新的字段

# ❌ 禁止：改状态对象再返回整个 state
def bad_node(state: SummaryState) -> SummaryState:
    state["summary"] = "..."
    return state
```

### 5.3 组装与编译

```python
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from typing import Literal

def review_summary(state: SummaryState) -> Command[Literal["regenerate", "finalize"]]:
    # HITL：暂停等用户确认。interrupt 的值会推给前端展示
    decision = interrupt({"summary": state["summary"]})
    if decision["action"] == "adjust":
        return Command(update={"messages": [decision["feedback"]]}, goto="regenerate")
    return Command(goto="finalize")

def finalize(state: SummaryState) -> dict:
    return {"summary": state["summary"]}

builder = (
    StateGraph(SummaryState)
    .add_node("generate", generate_summary)
    .add_node("review", review_summary)
    .add_node("regenerate", generate_summary)
    .add_node("finalize", finalize)
    .add_edge(START, "generate")
    .add_edge("generate", "review")
    .add_edge("regenerate", "review")
    .add_edge("finalize", END)
)
graph = builder.compile(checkpointer=checkpointer)  # 必须 compile() 才能调用
```

恢复执行（用户点击"确认"后，API 层调用）：

```python
from langgraph.types import Command

config = {"configurable": {"thread_id": f"record-{record_id}"}}
graph.invoke(Command(resume={"action": "approve"}), config=config)
```

规则：
- 用了 `Command(goto=...)` 的节点**不要再给它挂静态 `add_edge` 出边**——静态边和动态 goto 会同时执行。
- 路由回起点时用一个命名节点，**禁止 `add_edge(node, START)`**（START 只能作入口）。
- 检查图是否有到 END 的路径，避免环死循环。

## 6. HITL（人工确认）规范

- 暂停用 `interrupt(payload)`，恢复用 `Command(resume=value)`，这是 1.x 唯一推荐方式。
- **挂了 checkpointer 的图才能跨进程/跨天恢复**——"用户隔天确认总结"依赖这一点。
- interrupt 的 payload 要自带前端渲染所需信息（如待确认的总结全文），不要只传个 ID 让前端再查一遍。

## 7. 持久化（checkpointer）

| 场景 | 用什么 |
|---|---|
| 生产（Supabase Postgres） | `AsyncPostgresSaver`（`langgraph.checkpoint.postgres.aio`） |
| 本地开发 / 单测 | `SqliteSaver`（aiosqlite）或 `InMemorySaver` |

```python
# 生产：FastAPI 异步应用用 Async 版本
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

checkpointer = AsyncPostgresSaver.from_conn_string(settings.database_url)
await checkpointer.setup()          # 首次部署执行一次，建表；不要每次启动都跑
graph = builder.compile(checkpointer=checkpointer)
```

规则：
- **每次 invoke 必传 `thread_id`**（放 `config["configurable"]`），无 thread_id 状态不持久化。命名要有业务含义：`record-{id}`、`chat-{session_id}`。
- `setup()` 只在部署/初始化时执行，不是每次启动。
- **Checkpoint ≠ 业务事实**：HITL 确认结果、总结版本链等长期事实必须落业务表（`ai_summaries` 等）；Checkpoint 仅供暂停/恢复运行态，禁止从 checkpoint 表读业务数据（不手工查询 langgraph schema）。

## 8. 流式输出

AI 问答 SSE 场景用 `stream_mode="messages"` 逐 token 输出：

```python
async for chunk in graph.astream(
    {"messages": [("user", question)]},
    config=config,
    stream_mode="messages",
):
    token, metadata = chunk
    if token.content:
        yield token.content   # 经 sse-starlette 推给前端
```

节点内想上报进度（非 token）用 `get_stream_writer()` + `stream_mode="custom"`。

## 9. 错误处理

| 错误类型 | 策略 |
|---|---|
| 网络抖动、限流（瞬时） | `add_node(..., retry_policy=RetryPolicy(max_attempts=3, initial_interval=1.0))` |
| 工具执行失败（LLM 可自救） | `ToolNode(tools, handle_tool_errors=True)`，错误作为 ToolMessage 回给 LLM |
| 缺用户输入 | `interrupt(...)` |
| 未知异常 | 直接抛出，由 FastAPI 全局异常处理器兜底 + loguru 记录 |

## 10. RAG 检索红线（pgvector）

向量存储用自建 `semantic_embeddings` 表（数据模型 §4.6，统一管理向量生命周期与软删），**不用** `langchain-postgres` 的 PGVector collection（它会自建独立表，与该设计冲突）。检索经 `services/` 封装层用 SQLAlchemy 原生 SQL 执行：

```python
from sqlalchemy import text

# ✅ 唯一允许的方式：封装层强制注入过滤，三条件缺一不可
#   user_id + deleted_at IS NULL 必带；course_id 视挂载范围（@课程带、@全部资料不带）
async def search_segments(session: AsyncSession, query_vec: list[float], *,
                          user_id: UUID, course_id: UUID | None, k: int = 5):
    sql = """
        SELECT source_type, source_id, content,
               1 - (embedding <=> :vec::vector) AS score
        FROM semantic_embeddings
        WHERE user_id = :user_id
          AND deleted_at IS NULL
          {course_filter}
        ORDER BY embedding <=> :vec::vector
        LIMIT :k
    """.format(course_filter="AND course_id = :course_id" if course_id else "")
    rows = (await session.execute(text(sql), {
        "vec": str(query_vec), "user_id": user_id, "course_id": course_id, "k": k,
    })).all()
    return rows
```

规则：
- Graph 节点不得直接拼向量查询，一律走封装函数（由它注入过滤条件），**禁止裸相似度查询**。
- embedding 维度 1024 与表定义 `vector(1024)` 强一致；索引与查询必须用同一个 embedding 模型。
- v1.5 裁决 #24：`course_id` 可空——Inbox/未分类内容照常入索引，@全部资料全局检索时省略 course_id 条件，但 `user_id` 与 `deleted_at IS NULL` 永不省略。

## 11. LLM 调用埋点（llm_call_logs）

自建 `llm_call_logs` 表替代 Langfuse 自托管（v3.2 裁决），埋点规则：

- **埋在统一封装层**（`agents/llm.py` 的调用包装 / LangChain callback），Graph 节点代码不手写埋点——节点只管业务，观测在工厂层一次接入。
- 每次调用记录字段 = 数据模型 §4.10：`request_id`、`graph_name`、`graph_node`、`model`、`prompt_version`、`token_usage_json`、`latency_ms`、`error_code`（embedding 调用记 `embedding_model`）。
- **隐私红线**：不记 prompt 与输出全文（同 fastapi.md §7.1）；埋点失败不得影响主流程（吞掉并 loguru 记 error code）。

## 12. 反模式速查

| 禁止 | 用什么代替 |
|---|---|
| `AgentExecutor` / `create_react_agent` / 0.x chains | `create_agent()` / StateGraph |
| `ChatTongyi` 专有集成 | `ChatOpenAI` + DashScope `base_url` |
| 安装 monolithic 旧版 `langchain` 0.x | 拆分包（§1 清单）+ uv 锁定 |
| 节点内直接改 state / 返回整个 state | 返回部分更新 dict |
| 列表状态字段不加 reducer | `Annotated[list, operator.add]` |
| 不传 `thread_id` 直接 invoke | 始终带 `thread_id` |
| 生产用 `InMemorySaver` | `AsyncPostgresSaver` |
| `add_edge(node, START)` | 指向命名节点 |
| 裸向量相似度查询（缺过滤条件） | 封装层强制 user_id + deleted_at 过滤，course_id 视范围 |
| 确定性业务逻辑（CRUD/EvidenceBuilder/MasteryEngine）进 Graph | 普通确定性 Python Service |
| 节点直写 mastery 类表 | 只发 Learning Event（Mastery Engine 唯一写入口） |
| 把业务事实只存 Checkpoint / 手工查 langgraph schema | 长期事实落业务表 |
| 用 langchain-postgres PGVector collection | 自建 `semantic_embeddings` 表 + 原生 SQL |
| 节点里手写埋点 / 记 prompt 全文 | 工厂层统一埋 `llm_call_logs`，只记元数据 |
| 在节点里同步执行 ASR/ffmpeg 等重活 | 丢给 procrastinate worker，节点只编排 |

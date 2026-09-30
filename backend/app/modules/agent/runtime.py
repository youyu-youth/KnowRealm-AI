"""Agent 统一运行时上下文（通用 Agent 第一阶段工单 01）。

单 ContextVar 承载每轮流式生成的全部工具运行期状态：会话工厂、会话 id、
范围与挂载对象 id、模式、联网供应商、工具调用预算与页面快照。此前四个
工具各持一对 ContextVar 绑定（search_library / web_search / propose_memory /
propose_ingest），随操作工具族上线收敛为单对 bind/reset，消除每工具一对
绑定的复制增长（spec 实施决策 13）；02/03 的操作工具直接加入同一上下文。
"""

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import tzinfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.schemas import ChatMode, ChatPageSnapshot, ChatScope
from app.modules.search.web_search import SearchProvider
from app.modules.settings.config import LlmProviderConfig


@dataclass
class ToolCallBudget:
    """每轮（每条用户消息）的工具调用预算累计器：随运行时上下文每轮重建。

    资料检索（search_library）与对象查询（search_courses）共用同一预算
    （spec 实施决策 16：调用数与字符数累计）；operations_created 是操作类
    提案的独立累计（每轮上限 MAX_OPERATION_PROPOSALS_PER_TURN）。
    """

    calls_used: int = 0
    chars_fed: int = 0
    operations_created: int = 0


# 每轮工具调用次数上限（contract §3 冻结值；共享预算，执法点在各工具内，
# 工单 01 起随 ToolCallBudget 收敛到本模块，02/03 操作工具同源引用）。
MAX_TOOL_CALLS_PER_TURN = 6

# 每轮操作类提案上限（spec 实施决策 16：超限拒绝而非截断——截断会让确认卡
# 出现用户没见过的操作；量级对齐既有提案工具先例）。
MAX_OPERATION_PROPOSALS_PER_TURN = 5


@dataclass
class AgentRuntimeContext:
    """每轮流式生成前绑定、工具执行期读取的统一运行时上下文。

    - scope/record_id/library_item_id/course_id 语义沿用原 LibrarySearchContext：
      course_id 为检索边界课程（RECORD=记录所属课程、LIBRARY_ITEM=资料所属
      课程、COURSE=挂载课程、ALL=None），同时充当 propose_ingest 的提案课程；
    - web_search_provider 非 None 表示本轮联网生效（工具挂载与凭据同源）；
    - page 为随本轮消息携带的页面快照（提示性信息，不落库、不构成授权）。
    """

    session_factory: async_sessionmaker[AsyncSession]
    session_id: str
    scope: ChatScope = ChatScope.FREE
    mode: ChatMode = ChatMode.ASK
    course_id: str | None = None
    record_id: str | None = None
    library_item_id: str | None = None
    web_search_provider: SearchProvider | None = None
    # 聊天供应商（工单 02）：generate_learning_plan 等工具内 LLM 结构化生成用，
    # 与聊天主模型同源同配置；accept 已校验配置可用，此处恒非 None（测试上下文
    # 可缺省，工具侧自行结构化拒绝）。
    llm_provider: LlmProviderConfig | None = None
    page: ChatPageSnapshot | None = None
    # 授权档位（工单 02，spec 决策 9/10）：消息流入口解析（全局默认＋请求
    # 会话覆盖）后的当轮生效档；操作提交路径按它确定性分流，提示词与工具
    # 描述不随档位改变。
    auth_mode: AuthMode = AuthMode.REQUEST_APPROVAL
    # 触发指令摘录与消息引用（工单 02）：直执行回执 authorization_json 的
    # 授权依据素材，每轮流式生成前由 message_service 填入。
    instruction_excerpt: str | None = None
    message_id: str | None = None
    # 用户时区（时间能力 v1）：accept 从偏好解析（timezone 优先、未设置回退
    # 系统本地），时间工具族的默认时区；None=测试上下文缺省，工具侧回退 UTC。
    user_timezone: tzinfo | None = None
    budget: ToolCallBudget = field(default_factory=ToolCallBudget)


_agent_runtime_context: ContextVar[AgentRuntimeContext | None] = ContextVar(
    "agent_runtime_context", default=None
)


def bind_agent_runtime_context(
    context: AgentRuntimeContext,
) -> Token[AgentRuntimeContext | None]:
    return _agent_runtime_context.set(context)


def reset_agent_runtime_context(token: Token[AgentRuntimeContext | None]) -> None:
    _agent_runtime_context.reset(token)


def current_agent_runtime() -> AgentRuntimeContext | None:
    return _agent_runtime_context.get()

"""「建议保存」入库提案工具（研究会话 V1）：模型主动沉淀外部来源的唯一写路径。

研究会话中模型经 web_search 发现值得入库的外部来源时调用本工具创建
RESEARCH_INGEST 提案（创建不改任何事实、不抓取）；提案经前端就地确认卡
HITL 确认后，由 library 域应用器真实抓取入库。运行期上下文（session_factory
/ session_id / 范围课程）由统一 Agent 运行时上下文承载（工单 01 起，先例
propose_memory，见 agent/runtime.py）；scope=COURSE 自动带课程 id，ALL/FREE
落 None 由用户后续整理。
"""

import json

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from app.modules.agent.runtime import current_agent_runtime
from app.modules.library.proposals import ProposalService
from app.modules.library.schemas import ProposalCreateRequest, ProposalType

# 单次提案条数上限（对齐 propose_memory 的 5 条量级；超限拒绝而非截断：
# 截断会让确认卡出现用户没见过的来源）。
PROPOSE_INGEST_SOURCES_LIMIT = 5
# 单条限长：URL 常规上限；标题对齐 citation record_title 的 200 字。
PROPOSE_INGEST_URL_MAX_CHARS = 2048
PROPOSE_INGEST_TITLE_MAX_CHARS = 200


class IngestSource(BaseModel):
    """单个建议保存的外部来源；形状与 ResearchIngestPayload 的 url/title 对齐。"""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=PROPOSE_INGEST_URL_MAX_CHARS)
    title: str = Field(min_length=1, max_length=PROPOSE_INGEST_TITLE_MAX_CHARS)


# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
PROPOSE_INGEST_TOOL_NAME = "propose_ingest"


@tool
async def propose_ingest(sources: list[IngestSource]) -> str:
    """研究过程中发现值得保存进资料库的外部网页来源时使用。

    只建议真实出现在本轮 web_search 结果中的来源（URL 与标题照抄搜索结果，
    不得编造或修改）；一次最多 5 条。创建的是待用户确认的入库提案，用户逐条
    确认后才会真正抓取入库；调用成功后告知用户已生成建议保存提案、等待其确认。
    """
    context = current_agent_runtime()
    if context is None:
        return json.dumps(
            {"ok": False, "error": "RESEARCH_INGEST_CONTEXT_UNBOUND"}, ensure_ascii=False
        )
    if not sources:
        return json.dumps(
            {"ok": False, "error": "RESEARCH_SOURCES_EMPTY", "detail": "没有可建议保存的来源"},
            ensure_ascii=False,
        )
    if len(sources) > PROPOSE_INGEST_SOURCES_LIMIT:
        return json.dumps(
            {
                "ok": False,
                "error": "RESEARCH_SOURCES_TOO_LONG",
                "detail": (
                    f"一次最多建议保存 {PROPOSE_INGEST_SOURCES_LIMIT} 条来源，请挑最有价值的提交"
                ),
            },
            ensure_ascii=False,
        )
    created: list[dict[str, str]] = []
    async with context.session_factory() as session:
        for source in sources:
            proposal = await ProposalService.create(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.RESEARCH_INGEST,
                    payload={
                        "url": source.url,
                        "title": source.title,
                        "course_id": context.course_id,
                    },
                    session_id=context.session_id,
                ),
            )
            created.append({"proposal_id": proposal.id, "url": source.url, "title": source.title})
    return json.dumps({"ok": True, "proposals": created, "status": "PENDING"}, ensure_ascii=False)

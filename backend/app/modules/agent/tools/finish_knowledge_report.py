"""框架校验并直接结束子图的报告出口，不执行领域操作或消耗检索额度。"""

import json

from langchain_core.tools import tool

from app.modules.agent.delegations.schemas import KnowledgeReport


@tool("KnowledgeReport", args_schema=KnowledgeReport, return_direct=True)
async def finish_knowledge_report(
    summary: str, gaps: list[str], citation_lines: list[str] | None = None
) -> str:
    """结束知识任务并提交报告；最终必须单独调用，不与检索同时调用。

    summary 包含已有证据与结论，逐字引用行单独填 citation_lines；gaps 只列 task
    明确要求仍未回答的部分，回答了 task 则必须为空。未要求的扩展话题不列缺口。
    只提交报告，不检索、不写业务，也不构成授权。
    """
    return json.dumps(
        {"summary": summary, "gaps": gaps, "citation_lines": citation_lines or []},
        ensure_ascii=False,
    )

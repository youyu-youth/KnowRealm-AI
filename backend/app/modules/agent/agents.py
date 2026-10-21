"""首期固定 Agent 目录；能力装配仍由共享 graph 工厂负责。"""

from fastapi import APIRouter, Depends

from app.modules.agent.schemas import AgentId, AgentOut
from app.shared.deps import require_launch_token

AGENTS = (
    AgentOut(id=AgentId.GENERAL, purpose="general_assistance", read_only=False),
    AgentOut(id=AgentId.KNOWLEDGE, purpose="local_knowledge", read_only=True),
)

router = APIRouter(
    prefix="/api/agents", tags=["agents"], dependencies=[Depends(require_launch_token)]
)


@router.get("", response_model=list[AgentOut])
async def list_agents() -> list[AgentOut]:
    return list(AGENTS)

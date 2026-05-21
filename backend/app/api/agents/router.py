from fastapi import APIRouter

from app.agents.registry import AgentRegistry

router = APIRouter()


@router.get("/agents")
async def list_agents():
    return {"agents": AgentRegistry.list_agents()}

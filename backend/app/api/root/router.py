from fastapi import APIRouter

from app.agents.registry import AgentRegistry

router = APIRouter()


@router.get("/")
async def root():
    return {"status": "running", "agents": AgentRegistry.list_agents()}

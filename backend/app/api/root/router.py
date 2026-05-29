from fastapi import APIRouter

from app.nodes.registry import NodesRegistry

router = APIRouter()


@router.get("/")
async def root():
    return {"status": "running", "nodes": NodesRegistry.list_nodes()}

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.core.observability import get_logger, setup_observability, REQUEST_COUNTER, REQUEST_LATENCY, TOKEN_USAGE
from app.api.nodes.router import router as agents_router
from app.api.chat.router import router as chat_router
from app.api.root.router import router as root_router
from app.api.workflows.router import router as workflows_router
from app.api.observability.router import router as obs_router
from app.api.categories.router import router as categories_router
from app.nodes.registry import NodesRegistry

load_dotenv()

app = FastAPI(title="Enterprise LLM Gateway", version="0.2.3")
app = setup_observability(app)
logger = get_logger()


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ====================== Startup - Register Nodes ======================
@app.on_event("startup")
async def startup_event():
    logger.info("starting_gateway", version="0.2.3")
    # Dynamic discovery now handles all registrations automatically
    NodesRegistry.auto_discover()
    # Initial sync with DB to load persisted property overrides into the registry
    await NodesRegistry.sync_with_db()
    logger.info("nodes_registered", count=len(NodesRegistry.list_nodes()))
    
app.include_router(root_router)
app.include_router(agents_router)
app.include_router(chat_router)
app.include_router(workflows_router)
app.include_router(obs_router)
app.include_router(categories_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

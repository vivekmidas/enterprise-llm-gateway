from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.core.observability import get_logger, setup_observability, REQUEST_COUNTER, REQUEST_LATENCY, TOKEN_USAGE
from app.api.nodes.router import router as agents_router
# from app.api.chat.router import router as chat_router
from app.api.root.router import router as root_router
from app.api.workflows.router import router as workflows_router
from app.api.admin.router import router as admin_router
from app.api.admin.oauth import router as auth_router
from app.api.observability.router import router as obs_router
from app.api.categories.router import router as categories_router
from app.api.auth.router import router as base_auth_router
from app.api.webhooks import email as email_webhooks
from app.api.webhooks import run as run_webhooks
from app.nodes.registry import NodesRegistry

from app.api.admin.users import router as users

from app.core.database import init_db
from app.workflows.service import workflow_auto_discover
from app.core.security.jwt import AuthenticationMiddleware
from app.api.knowledge.router import router as knowledge_router

load_dotenv()

app = FastAPI(title="Enterprise LLM Gateway", version="0.2.3")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=1,
)

app = setup_observability(app)
logger = get_logger()
# ====================== Startup - Register Nodes ======================
@app.on_event("startup")
async def startup_event():
    """
    Handles the application startup lifecycle.
    1. Initializes the database schema.
    2. Automatically discovers all available nodes (built-in and plugins).
    3. Activates triggers for all enabled workflows to start background listeners.
    """
    logger.info("starting_gateway", version="0.2.3")
    
    # Initialize the database and ensure all tables exist
    await init_db()
    
    # Scan the project for node definitions and register them in memory
    await NodesRegistry.node_auto_discover()
    logger.info("nodes_registered", count=len(NodesRegistry.list_nodes()))

    # Sync workflow runnability status
    from app.core.database import AsyncSessionLocal
    from app.workflows.service import sync_workflows_runnability
    async with AsyncSessionLocal() as session:
        await sync_workflows_runnability(session)
    
    # Find all workflows marked as 'enabled' in the DB and activate their trigger nodes
    # (e.g., starting webhook servers or cron tasks).
    await workflow_auto_discover()
    logger.info("workflows_registered")
   
app.add_middleware(AuthenticationMiddleware)
app.include_router(root_router)
app.include_router(agents_router)
#app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(workflows_router)
app.include_router(obs_router)
app.include_router(categories_router)
app.include_router(auth_router)
app.include_router(base_auth_router)
app.include_router(email_webhooks.router)
app.include_router(run_webhooks.router)
app.include_router(users.router)
app.include_router(knowledge_router)
app.include_router(jobs_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)

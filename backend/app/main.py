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
from app.api.jobs import router as jobs_router
from app.api.admin.companies.router import router as company_router

from app.api.admin.users import router as users

from app.core.database import init_db
from app.workflows.service import workflow_auto_discover
from app.core.security.jwt import AuthenticationMiddleware
from app.api.knowledge.router import router as knowledge_router

load_dotenv()

app = FastAPI(title="Enterprise LLM Gateway", version="0.2.3")

app.add_middleware(AuthenticationMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:3001", "http://127.0.0.1:3001"],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=3600,
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
    # Seed default provider presets if missing
    from app.core.seed_provider_presets import seed_provider_presets
    from app.db.seed_rbac import seed_rbac
    async with AsyncSessionLocal() as session:
        await sync_workflows_runnability(session)
        await seed_provider_presets(session)
        await seed_rbac(session)
    
    # Find all workflows marked as 'enabled' in the DB and activate their trigger nodes
    # (e.g., starting webhook servers or cron tasks).
    await workflow_auto_discover()
    logger.info("workflows_registered")

    # Start EKP V3 Independent Background Worker Cron Loop
    import asyncio
    from app.knowledge.ekp_v3.worker import start_background_cron_loop
    asyncio.create_task(start_background_cron_loop(30))
    logger.info("ekp_v3_background_worker_started")
from app.api.llm_profiles import router as llm_profiles_router
from app.api.profiles.router import router as profiles_router
from app.api.playground import router as playground_router
from app.api.admin.provider_presets import router as provider_presets_router

from app.api.knowledge.ekp_router import router as ekp_router

from app.api.roles.router import router as roles_router

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
app.include_router(ekp_router)
app.include_router(jobs_router)
app.include_router(company_router)
app.include_router(llm_profiles_router)   # customer specific LLM profiles router with role projection
app.include_router(profiles_router)        # new structured profiles API
app.include_router(playground_router)
app.include_router(provider_presets_router)
# BLOCK COMMENT: REGISTER ADMIN BACKUP ROUTER (REQUIREMENT 3 DUMP EXPORTER)
from app.api.admin.backup import router as backup_router
app.include_router(backup_router)

app.include_router(roles_router)





if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)

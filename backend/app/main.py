from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.core.observability import setup_observability

load_dotenv()

app = FastAPI(title="Enterprise LLM Gateway", version="0.2.3")
logger = setup_observability(app)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.agents.router import router as agents_router
from app.api.chat.router import router as chat_router
from app.api.root.router import router as root_router
from app.api.workflows.router import router as workflows_router
from app.api.observability.router import router as obs_router
from app.agents.registry import AgentRegistry

# ====================== Startup - Register Agents ======================
@app.on_event("startup")
async def startup_event():
    logger.info("starting_gateway", version="0.2.3")
    AgentRegistry.auto_discover()
    
    # Register all built-in agents
    from app.agents.built_in.presidio.presidio_ner_guard_agent import PresidioNERGuardAgent
    from app.agents.built_in.profanity_guard_agent import ProfanityGuardAgent
    from app.agents.built_in.custom_rule_guard_agent import CustomRuleGuardAgent
    from app.agents.built_in.context_setter_agent import ContextSetterAgent
    from app.agents.built_in.sentiment_analyzer_agent import SentimentAnalyzerAgent
    from app.agents.built_in.output_guard_agent import OutputGuardAgent

    for agent_class in [PresidioNERGuardAgent, ProfanityGuardAgent, CustomRuleGuardAgent,
                       ContextSetterAgent, SentimentAnalyzerAgent, OutputGuardAgent]:
        AgentRegistry.register(agent_class())

    logger.info("agents_registered", count=len(AgentRegistry.list_agents()))
    
app.include_router(root_router)
app.include_router(agents_router)
app.include_router(chat_router)
app.include_router(workflows_router)
app.include_router(obs_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

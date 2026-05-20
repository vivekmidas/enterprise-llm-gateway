from fastapi import FastAPI, HTTPException
import uuid
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Dict, Any, Optional
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(
    title="Enterprise LLM Gateway",
    description="Secure, Guarded & Extensible LLM Workflow Engine",
    version="0.2.2"
)

# ======================
# Pydantic Models
# ======================
class ChatRequest(BaseModel):
    message: str
    workflow_id: str = "default"
    user_id: Optional[str] = None
    context: Dict[str, Any] = {}

class ChatResponse(BaseModel):
    trace_id: str
    final_response: str
    violations: list = []
    masked_content: str = ""
    status: str

# ======================
# Imports for Agents
# ======================
from app.agents.base import AgentInput
from app.agents.registry import AgentRegistry

# ====================== CORS (Critical for Docker + Frontend) ======================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================
# Auto Load Agents on Startup
# ======================
@app.on_event("startup")
async def startup_event():
    print("🚀 Starting Enterprise LLM Gateway...")
    AgentRegistry.auto_discover()
    
    # Register built-in agents
    from app.agents.built_in.presidio.presidio_ner_guard_agent import PresidioNERGuardAgent
    from app.agents.built_in.profanity_guard_agent import ProfanityGuardAgent
    from app.agents.built_in.custom_rule_guard_agent import CustomRuleGuardAgent

    AgentRegistry.register(PresidioNERGuardAgent())
    AgentRegistry.register(ProfanityGuardAgent())
    AgentRegistry.register(CustomRuleGuardAgent())
    
    print(f"✅ Loaded {len(AgentRegistry.list_agents())} agents: {AgentRegistry.list_agents()}")

@app.get("/")
async def root():
    return {
        "status": "running",
        "version": "0.2.2",
        "loaded_agents": AgentRegistry.list_agents()
    }

@app.get("/agents")
async def list_agents():
    return {"agents": AgentRegistry.list_agents()}

# ======================
# MAIN CHAT ENDPOINT
# ======================
@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    trace_id = str(uuid.uuid4())
    
    try:
        content = request.message
        violations = []

        # Run Presidio NER Guard
        presidio_agent = AgentRegistry.get_agent("presidio_ner_guard")
        if presidio_agent:
            input_data = AgentInput(
                trace_id=trace_id,
                content=content,
                context=request.context,
                config={"entities": ["PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON", "CREDIT_CARD"]}
            )
            result = await presidio_agent.run(input_data)
            content = result.content
            violations.extend(result.violations)

        # Run Profanity Guard
        profanity_agent = AgentRegistry.get_agent("profanity_guard")
        if profanity_agent:
            prof_input = AgentInput(
                trace_id=trace_id,
                content=content,
                context=request.context
            )
            prof_result = await profanity_agent.run(prof_input)
            content = prof_result.content
            violations.extend(prof_result.violations)

        return ChatResponse(
            trace_id=trace_id,
            final_response=f"Processed: {content[:300]}..." if len(content) > 300 else content,
            violations=violations,
            masked_content=content,
            status="flagged" if violations else "success"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
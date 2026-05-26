import uuid
import structlog

from fastapi import APIRouter, HTTPException

from app.api.chat.schemas import ChatRequest, ChatResponse
from app.api.chat.workflow import DEFAULT_CHAT_WORKFLOW
from app.workflows.executor import execute_dynamic_agent

router = APIRouter(prefix="/api")
logger = structlog.get_logger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    trace_id = str(uuid.uuid4())
    log = logger.bind(trace_id=trace_id, user_id=request.user_id, workflow_id=request.workflow_id)

    log.info("chat_request_started")

    try:
        result = await execute_dynamic_agent(
            agent_config=DEFAULT_CHAT_WORKFLOW,
            input_content=request.message,
            trace_id=trace_id,
            context={"user_id": request.user_id, **request.context},
        )

        log.info("chat_request_success", 
                 latency_ms=result.get("latency_ms"),
                 violations_count=len(result.get("violations", [])),
                 agents_executed=result.get("agents_executed")
        )

        return ChatResponse(
            trace_id=trace_id,
            final_response=result.get("final_response", result.get("content", "No response generated")),
            violations=result.get("violations", []),
            masked_content=result.get("masked_content", request.message),
            agents_executed=result.get("agents_executed", []),
            status="success",
        )

    except Exception as e:
        log.error("chat_request_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

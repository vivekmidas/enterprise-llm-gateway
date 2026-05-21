import uuid

from fastapi import APIRouter, HTTPException

from app.api.chat.schemas import ChatRequest, ChatResponse
from app.api.chat.workflow import DEFAULT_CHAT_WORKFLOW
from app.workflows.executor import execute_dynamic_workflow

router = APIRouter(prefix="/api")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    trace_id = str(uuid.uuid4())

    try:
        result = await execute_dynamic_workflow(
            workflow_config=DEFAULT_CHAT_WORKFLOW,
            input_content=request.message,
            trace_id=trace_id,
            context={"user_id": request.user_id, **request.context},
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
        raise HTTPException(status_code=500, detail=str(e))

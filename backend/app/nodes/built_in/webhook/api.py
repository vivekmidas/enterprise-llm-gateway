# backend/app/agents/built_in/context_setter_agent.py

from app.nodes.base import BaseNode, NodeInput, NodeOutput
import time
from app.core.observability import get_logger

logger = get_logger()

class WebhookAgent(BaseNode):
    name: str = "api_webhook_agent"
    description: str = "API Webhook Agent for external system integration"
    version: str = "1.0.0"

    async def validate_input(self, inp: NodeInput) -> NodeOutput:
        # Basic validation - can be extended with schema checks
        if not inp.content:
            return NodeOutput(
                trace_id=inp.trace_id,
                content=inp.content,
                status="failure",
                code=400,
                error_message="Content is required"
            )
        return NodeOutput(
            trace_id=inp.trace_id,
            content=inp.content,
            status="success"
        )

    async def execute (self, inp: NodeInput) -> NodeOutput:
        start = time.time()
        validation_result = await self.validate_input(inp)
        if validation_result.code == 200:
            logger.info(f"Input validation successful for trace_id: {inp.trace_id}")
        else:
            return validation_result

        return NodeOutput(
            trace_id=inp.trace_id,
            start_time=start,
            end_time=time.time(),
            content=enriched_content,
            metadata={"message": True, "source": "api_webhook"},
            latency_ms=round((time.time() - start) * 1000, 2)
        )
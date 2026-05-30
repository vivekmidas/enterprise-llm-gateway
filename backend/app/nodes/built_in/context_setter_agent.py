# backend/app/agents/built_in/context_setter_agent.py
from app.nodes.base import BaseNode, NodeInput, NodeOutput
import time

class ContextSetterAgent(BaseNode):
    name: str = "context_setter"
    description: str = "Enriches input with user context from CRM / DB"
    version: str = "1.0.0"

    async def run(self, inp: NodeInput) -> NodeOutput:
        start = time.time()
        
        # Simulate CRM lookup (replace with real API/DB call)
        user_context = {
            "customer_id": inp.context.get("user_id"),
            "segment": "premium",
            "last_interaction": "2025-05-20",
            "open_tickets": 0,
            **inp.context
        }

        enriched_content = f"User Context: {user_context}\n\nUser Message: {inp.content}"

        return NodeOutput(
            trace_id=inp.trace_id,
            start_time=start,
            end_time=time.time(),
            content=enriched_content,
            metadata={"context_fetched": True, "source": "crm"},
            latency_ms=round((time.time() - start) * 1000, 2)
        )
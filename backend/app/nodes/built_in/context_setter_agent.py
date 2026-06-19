from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
import time

class ContextSetterAgent(BaseNode):
    name: str = "context_setter"
    description: str = "Enriches input with user context from CRM / DB"
    version: str = "1.0.0"
    category: str = "Context Enrichment"

    async def validate_input(self, inp: NodeInput) -> NodeOutput:
        await super().validwate_input(inp)
        
        if not inp.context or "user_id" not in inp.context:
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_code=400,
                error_message=f"Context with user_id is required for ContextSetterAgent {self.name}"
            )
            
        return NodeOutput(
            trace_id=inp.trace_id,
            data=inp.data,
            error_code=200,
            status="success"
        )

    async def init(self) -> None:
        await super().init()
       
    async def execute (self, inp: NodeInput) -> NodeOutput:
        self.logger.info(f"Execution Started for  {self.name}")
        start = time.time()
        
        # Simulate CRM lookup (replace with real API/DB call)
        user_context = {
            "customer_id": inp.context.get("user_id"),
            "segment": "premium",
            "last_interaction": "2025-05-20",
            "open_tickets": 0,
            **inp.context
        }

        enriched_content = f"User Context: {user_context}\n\nUser Message: {inp.data}"
        self.logger.info(f"Execution Ended for  {self.name}")
  
        return NodeOutput(
            trace_id=inp.trace_id,
            start_time=start,
            end_time=time.time(),
            data=enriched_content,
            metadata={"context_fetched": True, "source": "crm"},
            # latency_ms=round((time.time() - start) * 1000, 2)
        )
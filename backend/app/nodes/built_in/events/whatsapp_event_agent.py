# backend/app/agents/built_in/context_setter_agent.py
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
import time
from app.core.observability import get_logger
logger = get_logger()
class ContextSetterAgent(BaseNode):
    name:str = "whatsapp_event_agent"
    description:str = "Activated when a new WhatsApp event is received"
    version:str = "1.0.0"
    category:str = "Context Enrichment"
    
    async def init(self) -> None:
        await super().init()
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        start = time.time()
        
        out_data = self.set_output_data(inp, "hi, context set from whatsapp event")
        return NodeOutput(
            trace_id=inp.trace_id,
            start_time=start,
            end_time=time.time(),
            data=out_data,
            metadata={"context_fetched": True, "source": "crm"},
            latency_ms=round((time.time() - start) * 1000, 2)
        )
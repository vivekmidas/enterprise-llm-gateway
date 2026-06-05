# backend/app/agents/built_in/context_setter_agent.py
from app.nodes.base import BaseNode, NodeInput, NodeOutput
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
        
       
        return NodeOutput(
            trace_id=inp.trace_id,
            start_time=start,
            end_time=time.time(),
            content="hi, context set from whatsapp event",
            metadata={"context_fetched": True, "source": "crm"},
            latency_ms=round((time.time() - start) * 1000, 2)
        )
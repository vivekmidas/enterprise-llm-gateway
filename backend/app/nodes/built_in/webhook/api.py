# backend/app/agents/built_in/context_setter_agent.py

from app.nodes.base import BaseNode, NodeInput, NodeOutput
import time
import json
import asyncio
from typing import List, Dict, Any
import uvicorn
from fastapi import FastAPI, Request
from app.core.observability import get_logger

logger = get_logger()

class WebhookAgent(BaseNode):
    name: str = "api_webhook_agent"
    description: str = "API Webhook Agent for external system integration"
    version: str = "1.0.0"
    category: str = "Integration"

    property_schema: List[Dict[str, Any]] = [
        {"key": "port", "label": "Listening Port", "type": "number", "placeholder": "8080"},
        {"key": "host", "label": "Host", "type": "string", "placeholder": "0.0.0.0"},
    ]

    properties: Dict[str, Any] = {
        "port": 8080,
        "host": "0.0.0.0"
    }

    async def init(self):
        await super().init()
        port = int(self.properties.get("port", 8080))
        host = self.properties.get("host", "0.0.0.0")
        workers = int(self.properties.get("workers", 1))
        log_level="debug"

        # Initialize the communication queue used by the execute() method
        self._queue = asyncio.Queue()

        # Setup FastAPI listener to receive incoming webhook data
        app = FastAPI()

        @app.get("/")
        async def webhook_endpoint(request: Request):
            try:
                payload = await request.json()
                await self._queue.put(payload)
                logger.info("webhook_received", payload=payload)
                return {"status": "received"}
            except Exception as e:
                logger.error(f"Error processing webhook: {e}")
                return {"status": "error", "message": str(e)}
           

        config = uvicorn.Config(app, host=host, port=port, workers=workers, log_level=log_level, access_log=False)
        server = uvicorn.Server(config)

        # Start the server as a background task to avoid event loop conflicts
        asyncio.create_task(server.serve())
        logger.info(f"webhook_agent_started on {host}:{port}")

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
        return None

    async def execute(self, inp: NodeInput) -> NodeOutput:
        start = time.time()
        
        try:
            logger.info("webhook_listener_waiting", trace_id=inp.trace_id)
            # Wait for data from the persistent queue (timeout after 60 seconds)
            payload = await asyncio.wait_for(self._queue.get(), timeout=60.0)
            
            return NodeOutput(
                trace_id=inp.trace_id,
                start_time=start,
                end_time=time.time(),
                content=json.dumps(payload),
                status="success",
                metadata={"source": "api_webhook"},
                latency_ms=round((time.time() - start) * 1000, 2)
            )
        except asyncio.TimeoutError:
            return NodeOutput(trace_id=inp.trace_id, status="failure", code=408, error_message="Webhook timed out")
        except Exception as e:
            return NodeOutput(trace_id=inp.trace_id, status="failure", code=500, error_message=str(e))
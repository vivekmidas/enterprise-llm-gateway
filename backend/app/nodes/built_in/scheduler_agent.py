import asyncio
import time
import subprocess
from typing import Any, Dict, List
from app.nodes.base import TriggerNode, NodeInput, NodeOutput

class SchedulerAgent(TriggerNode):
    """
    Agent that schedules a background task to run a command or another agent
    at a specific interval.
    """
    name:str = "scheduler_agent"
    description:str = "Runs a command or triggers an agent recurringly in the background"
    version:str = "1.0.0"
    category:str = "Custom"
    node_type: str = "trigger"
    property_schema: List[Dict[str, Any]] = [
        {"key": "interval", "label": "Interval", "type": "number"},
        {"key": "unit", "label": "Unit", "type": "choice", "options": ["seconds", "minutes"]},
        {"key": "command", "label": "Shell Command", "type": "string"},
        {"key": "targetAgent", "label": "Target Agent", "type": "choice", "options": []}
    ]
    properties: Dict[str, Any] = {
        "interval": 60,
        "unit": "seconds",
        "command": "",
        "targetAgent": ""
    }

    async def validate_input(self, inp: NodeInput) -> NodeOutput:
        await super().validate_input(inp)
        return NodeOutput(
            trace_id=inp.trace_id,
            content=inp.content,
            status="success"
        )

    async def init(self) -> None:
        await super().init()
        self._tasks: Dict[str, asyncio.Task] = {}

    async def activate(self, agent_node_id: str, workflow_config: Dict[str, Any]):
        """
        Starts a background asyncio task to fire the workflow at regular intervals.
        """
        # Call the parent activate to register the workflow_config in self._workflows
        await super().activate(agent_node_id, workflow_config)

        # Calculate delay based on interval and unit (seconds vs minutes)
        interval = float(self.properties.get("interval", self.default_node_properties.get("interval","6000")))
        unit = self.properties.get("unit", self.default_node_properties.get("unit","minutes"))
        delay = interval if unit == "seconds" else interval * 60

        if agent_node_id in self._tasks:
            self._tasks[agent_node_id].cancel()

        # Create a dedicated background loop for this instance
        self._tasks[agent_node_id] = asyncio.create_task(
            self._instance_scheduler_loop(agent_node_id, delay, workflow_config)
        )
        self.logger.info("scheduler_instance_activated", agent_node_id=agent_node_id, delay=delay)

    async def deactivate(self, agent_node_id: str):
        """
        Deactivates a specific scheduler instance by cancelling its background task.
        """
        if agent_node_id in self._tasks:
            self._tasks.pop(agent_node_id).cancel()
            self.logger.info("scheduler_instance_deactivated", agent_node_id=agent_node_id)

    async def _instance_scheduler_loop(self, agent_node_id: str, delay: float, workflow_config: Dict[str, Any]):
        """Background loop dedicated to a specific workflow instance."""
        while True:
            await asyncio.sleep(delay)
            try:
                self.logger.info("scheduler_firing", agent_node_id=agent_node_id)
                await self.execute_dynamic_agent(
                    agent_node_id=agent_node_id,
                    payload={ "message": "Hi my name is Cami, need help"}
                )
            except Exception as e:
                self.logger.error("scheduler_execution_failed", agent_node_id=agent_node_id, error=str(e))

    async def execute(self, inp: NodeInput) -> NodeOutput:
        """
        As a trigger node, when this is called inside the graph, 
        it simply passes the triggering payload forward.
        """
        return NodeOutput(
            trace_id=inp.trace_id,
            content=inp.content,
            status="success"
        )

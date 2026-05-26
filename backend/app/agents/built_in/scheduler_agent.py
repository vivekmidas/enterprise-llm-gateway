import asyncio
import time
import subprocess
import structlog
from typing import Any, Dict
from app.agents.built_in.base import BaseAgent, AgentInput, AgentOutput

logger = structlog.get_logger(__name__)

class SchedulerAgent(BaseAgent):
    """
    Agent that schedules a background task to run a command or another agent
    at a specific interval.
    """
    name = "scheduler_agent"
    description = "Runs a command or triggers an agent recurringly in the background"
    version = "1.0.0"
    category = "Custom"

    async def run(self, inp: AgentInput) -> AgentOutput:
        config = inp.config or {}
        interval = float(config.get("interval", 60))
        unit = config.get("unit", "seconds")
        command = config.get("command")
        target_agent = config.get("targetAgent")
        
        # Calculate delay in seconds
        delay = interval if unit == "seconds" else interval * 60
        
        # Fire and forget the scheduler loop in the background
        asyncio.create_task(self._scheduler_loop(delay, command, target_agent, inp))

        msg = f"Scheduler initiated: {interval} {unit} interval."
        if command:
            msg += f" Mode: command ('{command}')"
        if target_agent:
            msg += f" Mode: agent trigger ('{target_agent}')"

        return AgentOutput(
            trace_id=inp.trace_id,
            content=msg,
            status="success",
            metadata={
                "interval": interval,
                "unit": unit,
                "target_command": command,
                "target_agent": target_agent
            }
        )

    async def _scheduler_loop(self, delay: float, command: str, target_agent: str, original_input: AgentInput):
        # Deferred import to avoid circular dependency during registry auto-discovery
        from app.agents.registry import AgentRegistry
        
        log = logger.bind(
            scheduler_trace_id=original_input.trace_id, 
            delay=delay, 
            command=command, 
            target_agent=target_agent
        )
        log.info("scheduler_background_loop_started")
        
        while True:
            await asyncio.sleep(delay)
            try:
                if command:
                    log.info("scheduler_executing_command")
                    # Run shell command in a thread pool to avoid blocking the event loop
                    await asyncio.to_thread(
                        subprocess.run, 
                        command, 
                        shell=True, 
                        capture_output=True, 
                        text=True
                    )

                if target_agent:
                    agent = AgentRegistry.get_agent(target_agent)
                    if agent:
                        log.info("scheduler_triggering_agent")
                        # Create a fresh input for the periodic execution
                        execution_input = original_input.model_copy()
                        execution_input.trace_id = f"{original_input.trace_id}-auto-{int(time.time())}"
                        await agent.execute(execution_input)
                    else:
                        log.warning("scheduler_target_agent_not_found")
            
            except Exception as e:
                log.error("scheduler_execution_failed", error=str(e))
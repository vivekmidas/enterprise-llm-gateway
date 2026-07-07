# backend/app/workflows/executor.py
import json
import time
import structlog
from opentelemetry import trace
from typing import Any, Dict, List, Optional
from langgraph.types import RetryPolicy
from langgraph.graph import StateGraph, END, START
# try:
#     from langgraph.pregel.retry import RetryPolicy
# except ImportError:
#     # Fallback for versions where it's located in the private _retry module
#     from langgraph.pregel._retry import RetryPolicy

from app.utils.state import WorkflowState as AgentState
from app.nodes.base import NodeInput, NodeOutput
from app.nodes.registry import NodesRegistry
from app.core.llm_router import LLMRouter
from app.core.cache import trace_store

router = LLMRouter()
logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

def message_content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or json.dumps(item)))
            else:
                parts.append(str(item))
        return "\n".join(parts)

    return str(content)

class WorkflowExecutor:
    """
    Main executor class for dynamic agent workflows.
    Encapsulates graph execution.
    Provides both async and sync interfaces for calling systems.
    """
    # Centralized task registry mapping trace_id -> asyncio.Task
    active_tasks: Dict[str, Any] = {}

    def __init__(self, agent_config: Dict[str, Any], compiled_graph: Optional[Any] = None):
        self.agent_config = agent_config
        self.agent_id = agent_config.get("id")
        self.customer_id = agent_config.get("customer_id")
        self.user_id = agent_config.get("user_id")
        self.compiled_graph = compiled_graph
        self.agents_executed = []

        # Warm up cache or compile synchronously as a fallback
        if not self.compiled_graph and self.agent_id:
            version = str(self.agent_config.get("version", "1"))
            key = f"compiled_graph:{self.agent_id}:v{version}"
            from app.core.cache import workflow_cache
            if key in workflow_cache._local_compiled_cache:
                logger.info("using_locally_cached_graph_sync", agent_id=self.agent_id)
                self.compiled_graph = workflow_cache._local_compiled_cache[key]
            else:
                from app.workflows.service import compile_workflow_graph
                logger.info("cache_miss_compiling_graph_sync", agent_id=self.agent_id)
                try:
                    self.compiled_graph = compile_workflow_graph(self.agent_config)
                    # Cache locally
                    workflow_cache._local_compiled_cache[key] = self.compiled_graph
                except Exception as ce:
                    logger.error("sync_compilation_failed", agent_id=self.agent_id, error=str(ce))

    @classmethod
    def clear_graph_cache(cls, agent_id: Optional[str] = None):
        """Utility to clear cached compiled graphs. If agent_id is None, clear entire cache."""
        from app.core.cache import workflow_cache
        import asyncio
        
        async def _clear():
            if agent_id:
                await workflow_cache.invalidate_agent(agent_id)
            else:
                await workflow_cache.clear_all()
                
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(_clear())
            else:
                asyncio.run(_clear())
        except RuntimeError:
            asyncio.run(_clear())

    async def execute_async(self, input_content: str, trace_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Core execution logic (asynchronous)"""
        start_time = time.time()
        log = logger.bind(trace_id=trace_id)
        log.info("agent_execution_started", agent_id=self.agent_id)
        
        # Load compiled graph JIT using hybrid cache validation if not already set (e.g., in unit tests)
        if not self.compiled_graph:
            version = str(self.agent_config.get("version", "1"))
            if self.agent_id:
                from app.core.cache import workflow_cache
                cached = await workflow_cache.get_compiled_graph(self.agent_id, version)
                if cached is not None:
                    self.compiled_graph = cached
                else:
                    try:
                        from app.workflows.service import get_compiled_workflow
                        self.compiled_graph = await get_compiled_workflow(self.agent_id, version)
                    except Exception as ce:
                        logger.warning("jit_load_failed_falling_back", error=str(ce))
                        from app.workflows.service import compile_workflow_graph
                        self.compiled_graph = compile_workflow_graph(self.agent_config)
            else:
                from app.workflows.service import compile_workflow_graph
                self.compiled_graph = compile_workflow_graph(self.agent_config)

        ctx = dict(context or {})
        if "input_data" not in ctx:
            ctx["input_data"] = input_content

        state = AgentState(
            trace_id=trace_id,
            content=input_content,
            masked_content=input_content,
            context=ctx,
            metadata={},
            violations=[],
            llm_response="",
            final_response="",
            agents_executed=[]
        )
        
        # 1. Register task in the global active tasks registry
        import asyncio
        active_task = asyncio.current_task()
        if active_task:
            WorkflowExecutor.active_tasks[trace_id] = active_task
            
        # 2. Save initial "running" state to Redis trace store
        initial_trace = {
            "trace_id": trace_id,
            "workflow_id": self.agent_id,
            "workflow_name": self.agent_config.get("name"),
            "status": "running",
            "input": input_content,
            "output": "",
            "customer_id": self.customer_id,
            "user_id": self.user_id,
            "timestamp": start_time,
            "latency_ms": 0.0,
            "node_history": {},
            "context": context or {},
            "agents_executed": []
        }
        await trace_store.save_trace(trace_id, initial_trace)
        
        try:
            result = await self.compiled_graph.ainvoke(state)
        except asyncio.CancelledError as ce:
            log.warn("graph_execution_cancelled", error=str(ce))
            result_dict = state.model_dump()
            result_dict.update({
                "status": "stopped",
                "error_message": "Execution stopped by user",
                "final_response": "Workflow stopped by user",
                "trace_id": trace_id,
                "workflow_id": self.agent_id,
                "workflow_name": self.agent_config.get("name"),
                "customer_id": self.customer_id,
                "user_id": self.user_id,
                "latency_ms": round((time.time() - start_time) * 1000, 2),
                "timestamp": time.time()
            })
            await trace_store.save_trace(trace_id, result_dict)
            raise ce
        except Exception as e:
            log.error("graph_execution_failed", error=str(e))
            result_dict = state.model_dump()
            result_dict.update({
                "status": "failure",
                "error_message": str(e),
                "final_response": f"Workflow failed: {str(e)}",
                "trace_id": trace_id,
                "workflow_id": self.agent_id,
                "workflow_name": self.agent_config.get("name"),
                "customer_id": self.customer_id,
                "user_id": self.user_id,
                "latency_ms": round((time.time() - start_time) * 1000, 2),
                "timestamp": time.time()
            })
            await trace_store.save_trace(trace_id, result_dict)
            raise e
        finally:
            WorkflowExecutor.active_tasks.pop(trace_id, None)
            try:
                from app.workflows.service import clear_execution_cache
                clear_execution_cache(trace_id)
            except Exception as e:
                logger.warning("failed_to_clear_execution_cache", error=str(e))
 
        if isinstance(result, AgentState):
            result_dict = result.model_dump()
        elif isinstance(result, dict):
            result_dict = result.copy()
        else:
            result_dict = {}
 
        if result_dict.get("violations"):
            result_dict["status"] = "failure"
 
        result_dict["final_response"] = result_dict.get("llm_response") or result_dict.get("content", input_content)
        result_dict["trace_id"] = trace_id
        result_dict["workflow_id"] = self.agent_id
        result_dict["workflow_name"] = self.agent_config.get("name")
        result_dict["customer_id"] = self.customer_id
        result_dict["user_id"] = self.user_id
        result_dict["latency_ms"] = round((time.time() - start_time) * 1000, 2)
        result_dict["timestamp"] = time.time()
        
        # Set status as completed if it didn't fail
        if result_dict.get("status") not in ["failure", "stopped"]:
            result_dict["status"] = "completed"
 
        log.info("agent_execution_completed",
                 latency_ms=result_dict["latency_ms"],
                 violations_count=len(result_dict.get("violations", [])),
                 agents_count=len(result_dict.get("agents_executed", [])))
 
        await trace_store.save_trace(trace_id, result_dict)
        return result_dict
 
    def execute_sync(self, input_content: str, trace_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Synchronous entry point for the executor."""
        import asyncio
        try:
            return asyncio.run(self.execute_async(input_content, trace_id, context))
        except RuntimeError:
            # Handle case where an event loop is already running
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return loop.run_until_complete(self.execute_async(input_content, trace_id, context))
            else:
                raise
 
async def execute_dynamic_agent(
    agent_config: Dict[str, Any],
    input_content: str,
    trace_id: str,
    context: Optional[Dict[str, Any]] = None,
):
    """Helper function to execute a workflow using the WorkflowExecutor."""
    executor = WorkflowExecutor(agent_config)
    return await executor.execute_async(input_content, trace_id, context)

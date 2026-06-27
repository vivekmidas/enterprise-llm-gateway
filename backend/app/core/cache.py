import json
import time
import logging
from typing import Any, Optional, Dict, ClassVar
import redis.asyncio as redis

from app.core.config import get_settings, get_redis_client

settings = get_settings()
logger = logging.getLogger(__name__)

class WorkflowCache:
    """Handles hybrid caching for Compiled LangGraph objects."""
    client: ClassVar[redis.Redis] = get_redis_client()

    def __init__(self):
        self.ttl = settings.REDIS_CACHE_TTL
        self._local_compiled_cache: Dict[str, Any] = {}

    async def set_compiled_graph(self, agent_id: str, version: str, compiled_graph: Any) -> bool:
        """Cache compiled LangGraph object locally and store a validity token in Redis."""
        key = f"compiled_graph:{agent_id}:v{version or 'latest'}"
        try:
            # 1. Store the actual object in local memory
            self._local_compiled_cache[key] = compiled_graph
            
            # 2. Store a lightweight token in Redis for cross-worker invalidation
            await self.client.setex(key, self.ttl, "valid")
            
            logger.info(f"Cached compiled graph locally + Redis token: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to cache graph {key}: {e}")
            return False

    async def get_compiled_graph(self, agent_id: str, version: str | None = None) -> Optional[Any]:
        """Retrieve compiled graph from local memory, checking Redis for validity."""
        key = f"compiled_graph:{agent_id}:v{version or 'latest'}"
        try:
            # 1. Check local cache
            if key in self._local_compiled_cache:
                # 2. Check if the token still exists in Redis (hasn't been invalidated)
                if await self.client.exists(key):
                    logger.info(f"Hybrid cache hit for {key}")
                    return self._local_compiled_cache[key]
                else:
                    # Token gone? Invalidate local entry
                    logger.info(f"Cache token expired or invalidated for {key}")
                    del self._local_compiled_cache[key]
            
            return None
        except Exception as e:
            logger.error(f"Failed to get cached graph {key}: {e}")
            return None

    async def invalidate_agent(self, agent_id: str) -> None:
        """Invalidate all versions across Redis and local cache."""
        try:
            # 1. Clear local cache entries for this workflow
            prefix = f"compiled_graph:{agent_id}:"
            local_keys = [k for k in self._local_compiled_cache if k.startswith(prefix)]
            for k in local_keys:
                self._local_compiled_cache.pop(k, None)

            # 2. Delete tokens from Redis to notify other workers
            async for key in self.client.scan_iter(match=f"compiled_graph:{agent_id}:*"):
                await self.client.delete(key)
            logger.info(f"Invalidated cache for agent {agent_id}")
        except Exception as e:
            logger.warning(f"Cache invalidation failed for {agent_id}: {e}")

class TraceStore:
    """Dedicated class for handling execution traces and observability data."""
    client: ClassVar[redis.Redis] = get_redis_client()

    async def save_trace(self, trace_id: str, data: dict):
        """Store execution trace with a 24-hour TTL and index it by tenant, user, and globally."""
        key = f"trace:{trace_id}"
        customer_id = data.get("customer_id")
        user_id = data.get("user_id")
        now = time.time()
        try:
            # Store trace details as JSON string (decode_responses=True handles this)
            await self.client.setex(key, 86400, json.dumps(data))
            
            # 1. Global index (for system admins)
            await self.client.zadd("traces:index", {trace_id: now})
            await self.client.zremrangebyscore("traces:index", 0, now - 86400)
            
            # 2. Customer/Tenant index
            if customer_id is not None:
                cust_index_key = f"customer:{customer_id}:traces:index"
                await self.client.zadd(cust_index_key, {trace_id: now})
                await self.client.zremrangebyscore(cust_index_key, 0, now - 86400)
                
            # 3. User-specific index
            if user_id:
                user_index_key = f"user:{user_id}:traces:index"
                await self.client.zadd(user_index_key, {trace_id: now})
                await self.client.zremrangebyscore(user_index_key, 0, now - 86400)
                
        except Exception as e:
            logger.error(f"Failed to save trace {trace_id}: {e}")

    async def get_traces_in_range(
        self, 
        start_time: float, 
        limit: int = 100,
        customer_id: Optional[int] = None,
        user_id: Optional[str] = None,
        workflow_id: Optional[str] = None
    ):
        """Retrieve traces within a specific timestamp range, filtered by tenant/user and workflow."""
        try:
            # Determine which index to query based on role boundaries
            if customer_id is not None:
                index_key = f"customer:{customer_id}:traces:index"
            elif user_id:
                index_key = f"user:{user_id}:traces:index"
            else:
                index_key = "traces:index"
                
            trace_ids = await self.client.zrevrangebyscore(index_key, "+inf", start_time, start=0, num=limit)
            traces = []
            for tid in trace_ids:
                data = await self.client.get(f"trace:{tid}")
                if data:
                    trace_dict = json.loads(data)
                    # Filter by workflow_id in memory if specified
                    if workflow_id and trace_dict.get("workflow_id") != workflow_id:
                        continue
                    traces.append(trace_dict)
            return traces
        except Exception as e:
            logger.error(f"Failed to get traces in range: {e}")
            return []

# Singletons for application-wide use
workflow_cache = WorkflowCache()
trace_store = TraceStore()
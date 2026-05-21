import json
import pickle
import logging
from typing import Any, Optional
import redis.asyncio as redis
from redis.exceptions import RedisError
from functools import wraps

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class RedisCache:
    def __init__(self):
        self.client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=False,  # For pickled objects
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        self.ttl = settings.REDIS_CACHE_TTL

    async def set_compiled_graph(self, workflow_id: str, version: str, compiled_graph: Any) -> bool:
        """Cache compiled LangGraph object using pickle (fastest for complex objects)."""
        key = f"compiled_graph:{workflow_id}:v{version or 'latest'}"
        try:
            # Pickle the compiled graph (LangGraph objects are picklable)
            data = pickle.dumps(compiled_graph)
            await self.client.setex(key, self.ttl, data)
            logger.info(f"Cached compiled graph: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to cache graph {key}: {e}")
            return False

    async def get_compiled_graph(self, workflow_id: str, version: str | None = None) -> Optional[Any]:
        """Retrieve compiled graph from Redis."""
        key = f"compiled_graph:{workflow_id}:v{version or 'latest'}"
        try:
            data = await self.client.get(key)
            if data:
                graph = pickle.loads(data)
                logger.info(f"Cache hit for {key}")
                return graph
            return None
        except Exception as e:
            logger.error(f"Failed to get cached graph {key}: {e}")
            return None

    async def invalidate_workflow(self, workflow_id: str) -> None:
        """Invalidate all versions on save/update."""
        try:
            # Use scan for pattern delete (async)
            async for key in self.client.scan_iter(match=f"compiled_graph:{workflow_id}:*"):
                await self.client.delete(key)
            logger.info(f"Invalidated cache for workflow {workflow_id}")
        except Exception as e:
            logger.warning(f"Cache invalidation failed for {workflow_id}: {e}")

# Global singleton
redis_cache = RedisCache()
import json
import pickle
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging
from redis import Redis
from langgraph.graph.state import CompiledStateGraph  # StateGraph compiled

from ..models.workflow import WorkflowDefinition
from app.core.config import get_redis_client
from app.workflows.builder import build_graph_from_definition
from app.workflows.store import load_workflow_from_store

logger = logging.getLogger(__name__)

class CompiledGraphCache:
    """Redis + Local memory hybrid cache for compiled graphs"""
    
    def __init__(self, ttl_seconds: int = 3600):  # 1 hour default
        self.ttl = ttl_seconds
        self.local_cache: Dict[str, CompiledStateGraph] = {}  # per-process LRU
        self.redis = get_redis_client()
        self.prefix = "compiled_graph:"

    def _get_cache_key(self, workflow_id: str, version: Optional[str] = None) -> str:
        key = f"{workflow_id}:{version or 'latest'}"
        return self.prefix + hashlib.sha256(key.encode()).hexdigest()

    async def get(self, workflow_id: str, version: Optional[str] = None) -> Optional[CompiledStateGraph]:
        """Get compiled graph - check local -> Redis -> rebuild"""
        cache_key = self._get_cache_key(workflow_id, version)
        hash_key = cache_key  # for Redis

        # 1. Local process cache (fastest)
        if cache_key in self.local_cache:
            logger.debug(f"Cache hit (local): {workflow_id}")
            return self.local_cache[cache_key]

        # 2. Redis cache
        try:
            cached_data = await self.redis.get(hash_key)
            if cached_data:
                # We cannot reliably pickle CompiledGraph due to callables
                # So we store metadata + version, and rebuild if needed
                metadata = json.loads(cached_data)
                logger.debug(f"Cache hit (Redis metadata): {workflow_id}")
                
                # Rebuild and store locally - builder needs WorkflowDefinition object
                definition = await load_workflow_from_store(workflow_id, version)
                compiled = await build_graph_from_definition(definition)
                self.local_cache[cache_key] = compiled
                return compiled
        except Exception as e:
            logger.warning(f"Redis get failed for {workflow_id}: {e}")

        # 3. Miss - build fresh
        logger.info(f"Cache miss - building graph: {workflow_id}")
        definition = await load_workflow_from_store(workflow_id, version)
        compiled = await build_graph_from_definition(definition)
        
        # Cache locally + metadata in Redis
        self.local_cache[cache_key] = compiled
        await self._cache_metadata(workflow_id, version)
        
        return compiled

    async def _cache_metadata(self, workflow_id: str, version: Optional[str]):
        """Store lightweight metadata in Redis for invalidation"""
        key = self._get_cache_key(workflow_id, version)
        metadata = {
            "workflow_id": workflow_id,
            "version": version or "latest",
            "cached_at": datetime.utcnow().isoformat(),
            "ttl": self.ttl
        }
        try:
            await self.redis.setex(key, self.ttl, json.dumps(metadata))
        except Exception as e:
            logger.error(f"Failed to cache metadata: {e}")

    async def invalidate(self, workflow_id: str, version: Optional[str] = None):
        """Invalidate on workflow update (called from save_workflow)"""
        key = self._get_cache_key(workflow_id, version)
        try:
            await self.redis.delete(key)
            if key in self.local_cache:
                del self.local_cache[key]
            logger.info(f"Invalidated compiled graph cache: {workflow_id}")
        except Exception as e:
            logger.error(f"Cache invalidation failed: {e}")

    async def clear_all(self):
        """For admin/debug"""
        try:
            keys = await self.redis.keys(self.prefix + "*")
            if keys:
                await self.redis.delete(*keys)
            self.local_cache.clear()
            logger.info("Cleared all compiled graph cache")
        except Exception as e:
            logger.error(f"Clear cache failed: {e}")

# Global instance
graph_cache = CompiledGraphCache(ttl_seconds=1800)  # 30 min for production
from pydantic_settings import BaseSettings
from functools import lru_cache
import redis.asyncio as redis
import json

class Settings(BaseSettings):
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    REDIS_CACHE_TTL: int = 3600 * 6  # 6 hours for compiled graphs
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "sqlite+aiosqlite:///./enterprise_gateway.db"
    SECRET_KEY: str = "super-secret-change-this-in-production"
    ISSUER: str = "http://localhost.com"
    AUDIENCE: str = "enterprise"    
    ALGORITHM:str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES:int = 3600          # Short-lived
    REFRESH_TOKEN_EXPIRE_DAYS:int = 7
    KNOWLEDGE_STORAGE_PATH: str = "./data/knowledge"
    KNOWLEDGE_MAX_FILE_SIZE_MB: int = 25
    KNOWLEDGE_CHUNK_SIZE: int = 1000
    KNOWLEDGE_CHUNK_OVERLAP: int = 200
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION: str = "enterprise_knowledge"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_PROVIDER: str = "vllm"
    OLLAMA_MODEL: str = "qwen:0.5b"
    EMBEDDING_PROVIDER: str = "ollama" # change to "openai" if you want to use openai embeddings
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIMENSION: int = 768
    # EMBEDDING_PROVIDER: str = "openai"
    # EMBEDDING_MODEL: str = "text-embedding-3-small"
    # EMBEDDING_DIMENSION: int = 1536
    OPENAI_API_KEY: str | None = None
    RERANK_ENABLED: bool = True
    RERANK_PROVIDER: str = "ollama"
    RERANK_MODEL: str = "qwen3.5:0.8b"
    RERANK_CANDIDATE_LIMIT: int = 5
    SYSTEM_PROMPT: str = (
        "You are a helpful enterprise assistant. Answer the user's query using only the provided context. "
        "If the context does not contain enough information to answer the query, you must respond with 'I dont have response to the question' and nothing else. "
        "Do not try to make up or extrapolate any answers. Be polite"
    )

    class Config:
        env_file = ".env"
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    return Settings()

_loop_redis_clients = {}

def get_redis_client():
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    settings = get_settings()
    
    if loop:
        loop_id = id(loop)
        if loop_id not in _loop_redis_clients:
            _loop_redis_clients[loop_id] = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        return _loop_redis_clients[loop_id]
    else:
        return redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
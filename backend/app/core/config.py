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
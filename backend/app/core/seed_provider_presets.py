import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.db_models import ProviderPresetDB

logger = logging.getLogger(__name__)

STANDARD_PRESETS = [
    {
        "provider_key": "ollama",
        "name": "Ollama (Local)",
        "description": "Local open-source LLM & embedding engine via Ollama",
        "base_url": "http://localhost:11434",
        "chat_models": ["llama3.2", "qwen2.5-coder", "mistral", "llama3.1", "qwen3:0.6b"],
        "default_chat_model": "llama3.2",
        "embedding_models": [
            {"model": "nomic-embed-text", "dimension": 768},
            {"model": "bge-m3", "dimension": 1024},
            {"model": "mxbai-embed-large", "dimension": 1024},
            {"model": "all-minilm", "dimension": 384}
        ],
        "default_embedding_model": "nomic-embed-text",
        "default_embedding_dimension": 768,
        "rerank_models": ["qwen3:0.6b", "bge-reranker-large", "bge-reranker-base"],
        "default_rerank_model": "qwen3:0.6b",
        "default_temperature": 0.7,
        "default_max_tokens": 1024,
        "api_key_header": None,
        "is_active": True
    },
    {
        "provider_key": "vllm",
        "name": "vLLM Server",
        "description": "High-throughput vLLM inference engine with OpenAI-compatible API",
        "base_url": "http://localhost:8000/v1",
        "chat_models": ["meta-llama/Llama-3.1-8B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3"],
        "default_chat_model": "meta-llama/Llama-3.1-8B-Instruct",
        "embedding_models": [
            {"model": "BAAI/bge-m3", "dimension": 1024},
            {"model": "BAAI/bge-large-en-v1.5", "dimension": 1024},
            {"model": "intfloat/e5-large-v2", "dimension": 1024}
        ],
        "default_embedding_model": "BAAI/bge-m3",
        "default_embedding_dimension": 1024,
        "rerank_models": ["BAAI/bge-reranker-large", "BAAI/bge-reranker-v2-m3"],
        "default_rerank_model": "BAAI/bge-reranker-large",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "Authorization",
        "is_active": True
    },
    {
        "provider_key": "openai",
        "name": "OpenAI",
        "description": "Official OpenAI API (GPT-4o, text-embedding-3)",
        "base_url": "https://api.openai.com/v1",
        "chat_models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4-turbo"],
        "default_chat_model": "gpt-4o",
        "embedding_models": [
            {"model": "text-embedding-3-small", "dimension": 1536},
            {"model": "text-embedding-3-large", "dimension": 3072},
            {"model": "text-embedding-ada-002", "dimension": 1536}
        ],
        "default_embedding_model": "text-embedding-3-small",
        "default_embedding_dimension": 1536,
        "rerank_models": ["gpt-4o-mini", "cohere-rerank-v3"],
        "default_rerank_model": "gpt-4o-mini",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "Authorization",
        "is_active": True
    },
    {
        "provider_key": "grok",
        "name": "Grok / xAI",
        "description": "xAI Grok models with high reasoning performance",
        "base_url": "https://api.x.ai/v1",
        "chat_models": ["grok-2-latest", "grok-2-vision-1212", "grok-beta"],
        "default_chat_model": "grok-2-latest",
        "embedding_models": [
            {"model": "v1/embeddings", "dimension": 1536}
        ],
        "default_embedding_model": "v1/embeddings",
        "default_embedding_dimension": 1536,
        "rerank_models": ["grok-2-latest"],
        "default_rerank_model": "grok-2-latest",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "Authorization",
        "is_active": True
    },
    {
        "provider_key": "azure",
        "name": "Azure OpenAI",
        "description": "Microsoft Azure OpenAI Service deployments",
        "base_url": "https://{resource}.openai.azure.com",
        "chat_models": ["gpt-4o", "gpt-4o-mini", "gpt-35-turbo"],
        "default_chat_model": "gpt-4o",
        "embedding_models": [
            {"model": "text-embedding-3-small", "dimension": 1536},
            {"model": "text-embedding-3-large", "dimension": 3072}
        ],
        "default_embedding_model": "text-embedding-3-small",
        "default_embedding_dimension": 1536,
        "rerank_models": ["gpt-4o-mini"],
        "default_rerank_model": "gpt-4o-mini",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "api-key",
        "is_active": True
    },
    {
        "provider_key": "anthropic",
        "name": "Anthropic Claude",
        "description": "Anthropic Claude AI API",
        "base_url": "https://api.anthropic.com/v1",
        "chat_models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
        "default_chat_model": "claude-3-5-sonnet-20241022",
        "embedding_models": [],
        "default_embedding_model": None,
        "default_embedding_dimension": None,
        "rerank_models": ["claude-3-5-haiku-20241022"],
        "default_rerank_model": "claude-3-5-haiku-20241022",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "x-api-key",
        "is_active": True
    }
]

async def seed_provider_presets(db: AsyncSession, force: bool = False) -> int:
    """
    Seed standard default provider presets into DB if missing or if force=True.
    Returns count of added/updated presets.
    """
    count = 0
    for preset_data in STANDARD_PRESETS:
        result = await db.execute(
            select(ProviderPresetDB).where(ProviderPresetDB.provider_key == preset_data["provider_key"])
        )
        existing = result.scalar_one_or_none()

        if not existing:
            new_preset = ProviderPresetDB(**preset_data)
            db.add(new_preset)
            count += 1
        elif force:
            for k, v in preset_data.items():
                setattr(existing, k, v)
            count += 1

    if count > 0:
        await db.commit()
        logger.info("provider_presets_seeded", count=count)

    return count

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.db_models import ProviderPresetDB

logger = logging.getLogger(__name__)

STANDARD_PRESETS = [
    {
        "provider_key": "ollama",
        "name": "ollama",
        "display_name": "Ollama (Local)",
        "description": "Local open-source LLM & embedding engine via Ollama",
        "base_url": "http://localhost:11434",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/api/chat",
                "models": ["llama3.2", "qwen2.5-coder", "mistral", "llama3.1", "qwen3:0.6b"],
                "default_model": "llama3.2",
                "api_key": None,
                "payload_structure": {"payload_format": "ollama", "messages_key": "messages"}
            },
            {
                "name": "embedding",
                "endpoint": "/api/embeddings",
                "models": [
                    {"model": "nomic-embed-text", "dimension": 768},
                    {"model": "bge-m3", "dimension": 1024},
                    {"model": "mxbai-embed-large", "dimension": 1024},
                    {"model": "all-minilm", "dimension": 384}
                ],
                "default_model": "nomic-embed-text",
                "api_key": None,
                "payload_structure": {"payload_format": "ollama", "input_key": "prompt"}
            },
            {
                "name": "reranking",
                "endpoint": "/api/chat",
                "models": ["qwen3:0.6b", "bge-reranker-large", "bge-reranker-base"],
                "default_model": "qwen3:0.6b",
                "api_key": None,
                "payload_structure": {"payload_format": "ollama_chat_score"}
            }
        ],
        "chat_models": ["llama3.2", "qwen2.5-coder", "mistral", "llama3.1", "qwen3:0.6b"],
        "default_chat_model": "llama3.2",
        "search_endpoint": "/api/chat",
        "embedding_models": [
            {"model": "nomic-embed-text", "dimension": 768},
            {"model": "bge-m3", "dimension": 1024},
            {"model": "mxbai-embed-large", "dimension": 1024},
            {"model": "all-minilm", "dimension": 384}
        ],
        "default_embedding_model": "nomic-embed-text",
        "default_embedding_dimension": 768,
        "embedding_endpoint": "/api/embeddings",
        "rerank_models": ["qwen3:0.6b", "bge-reranker-large", "bge-reranker-base"],
        "default_rerank_model": "qwen3:0.6b",
        "rerank_endpoint": "/api/chat",
        "default_temperature": 0.7,
        "default_max_tokens": 1024,
        "api_key_header": None,
        "capability_configs": {
            "chat": {"payload_format": "ollama", "messages_key": "messages"},
            "embeddings": {"payload_format": "ollama", "input_key": "prompt"},
            "rerank": {"payload_format": "ollama_chat_score"}
        },
        "is_active": True
    },
    {
        "provider_key": "vllm",
        "name": "vllm",
        "display_name": "vLLM Server",
        "description": "High-throughput vLLM inference engine with OpenAI-compatible API",
        "base_url": "http://localhost:8000/v1",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/chat/completions",
                "models": ["meta-llama/Llama-3.1-8B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3"],
                "default_model": "meta-llama/Llama-3.1-8B-Instruct",
                "api_key": None,
                "payload_structure": {"payload_format": "openai", "messages_key": "messages"}
            },
            {
                "name": "embedding",
                "endpoint": "/embeddings",
                "models": [
                    {"model": "BAAI/bge-m3", "dimension": 1024},
                    {"model": "BAAI/bge-large-en-v1.5", "dimension": 1024},
                    {"model": "intfloat/e5-large-v2", "dimension": 1024}
                ],
                "default_model": "BAAI/bge-m3",
                "api_key": None,
                "payload_structure": {"payload_format": "openai", "input_key": "input"}
            },
            {
                "name": "reranking",
                "endpoint": "/rerank",
                "models": ["BAAI/bge-reranker-large", "BAAI/bge-reranker-v2-m3"],
                "default_model": "BAAI/bge-reranker-large",
                "api_key": None,
                "payload_structure": {"payload_format": "cohere_vllm_rerank"}
            }
        ],
        "chat_models": ["meta-llama/Llama-3.1-8B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3"],
        "default_chat_model": "meta-llama/Llama-3.1-8B-Instruct",
        "search_endpoint": "/chat/completions",
        "embedding_models": [
            {"model": "BAAI/bge-m3", "dimension": 1024},
            {"model": "BAAI/bge-large-en-v1.5", "dimension": 1024},
            {"model": "intfloat/e5-large-v2", "dimension": 1024}
        ],
        "default_embedding_model": "BAAI/bge-m3",
        "default_embedding_dimension": 1024,
        "embedding_endpoint": "/embeddings",
        "rerank_models": ["BAAI/bge-reranker-large", "BAAI/bge-reranker-v2-m3"],
        "default_rerank_model": "BAAI/bge-reranker-large",
        "rerank_endpoint": "/rerank",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "Authorization",
        "capability_configs": {
            "chat": {"payload_format": "openai", "messages_key": "messages"},
            "embeddings": {"payload_format": "openai", "input_key": "input"},
            "rerank": {"payload_format": "cohere_vllm_rerank"}
        },
        "is_active": True
    },
    {
        "provider_key": "openai",
        "name": "openai",
        "display_name": "OpenAI",
        "description": "Official OpenAI API (GPT-4o, text-embedding-3)",
        "base_url": "https://api.openai.com/v1",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/chat/completions",
                "models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4-turbo"],
                "default_model": "gpt-4o",
                "api_key": None,
                "payload_structure": {"payload_format": "openai", "messages_key": "messages"}
            },
            {
                "name": "embedding",
                "endpoint": "/embeddings",
                "models": [
                    {"model": "text-embedding-3-small", "dimension": 1536},
                    {"model": "text-embedding-3-large", "dimension": 3072},
                    {"model": "text-embedding-ada-002", "dimension": 1536}
                ],
                "default_model": "text-embedding-3-small",
                "api_key": None,
                "payload_structure": {"payload_format": "openai", "input_key": "input"}
            },
            {
                "name": "reranking",
                "endpoint": "/chat/completions",
                "models": ["gpt-4o-mini", "gpt-4o"],
                "default_model": "gpt-4o-mini",
                "api_key": None,
                "payload_structure": {"payload_format": "openai_chat_score"}
            }
        ],
        "chat_models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4-turbo"],
        "default_chat_model": "gpt-4o",
        "search_endpoint": "/chat/completions",
        "embedding_models": [
            {"model": "text-embedding-3-small", "dimension": 1536},
            {"model": "text-embedding-3-large", "dimension": 3072},
            {"model": "text-embedding-ada-002", "dimension": 1536}
        ],
        "default_embedding_model": "text-embedding-3-small",
        "default_embedding_dimension": 1536,
        "embedding_endpoint": "/embeddings",
        "rerank_models": ["gpt-4o-mini", "gpt-4o"],
        "default_rerank_model": "gpt-4o-mini",
        "rerank_endpoint": "/chat/completions",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "Authorization",
        "capability_configs": {
            "chat": {"payload_format": "openai", "messages_key": "messages"},
            "embeddings": {"payload_format": "openai", "input_key": "input"},
            "rerank": {"payload_format": "openai_chat_score"}
        },
        "is_active": True
    },
    {
        "provider_key": "cohere",
        "name": "cohere",
        "display_name": "Cohere (Rerank & Embed)",
        "description": "High-performance specialized reranking and embedding models from Cohere",
        "base_url": "https://api.cohere.com/v2",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/chat",
                "models": ["command-r-plus", "command-r", "command-light"],
                "default_model": "command-r",
                "api_key": None,
                "payload_structure": {"payload_format": "cohere"}
            },
            {
                "name": "embedding",
                "endpoint": "/embed",
                "models": [
                    {"model": "embed-english-v3.0", "dimension": 1024},
                    {"model": "embed-multilingual-v3.0", "dimension": 1024},
                    {"model": "embed-english-light-v3.0", "dimension": 384}
                ],
                "default_model": "embed-english-v3.0",
                "api_key": None,
                "payload_structure": {"payload_format": "cohere"}
            },
            {
                "name": "reranking",
                "endpoint": "/rerank",
                "models": ["rerank-v3.5", "rerank-english-v3.0", "rerank-multilingual-v3.0"],
                "default_model": "rerank-v3.5",
                "api_key": None,
                "payload_structure": {"payload_format": "cohere_rerank"}
            }
        ],
        "chat_models": ["command-r-plus", "command-r", "command-light"],
        "default_chat_model": "command-r",
        "search_endpoint": "/chat",
        "embedding_models": [
            {"model": "embed-english-v3.0", "dimension": 1024},
            {"model": "embed-multilingual-v3.0", "dimension": 1024},
            {"model": "embed-english-light-v3.0", "dimension": 384}
        ],
        "default_embedding_model": "embed-english-v3.0",
        "default_embedding_dimension": 1024,
        "embedding_endpoint": "/embed",
        "rerank_models": ["rerank-v3.5", "rerank-english-v3.0", "rerank-multilingual-v3.0"],
        "default_rerank_model": "rerank-v3.5",
        "rerank_endpoint": "/rerank",
        "default_temperature": 0.3,
        "default_max_tokens": 1024,
        "api_key_header": "Authorization",
        "capability_configs": {
            "rerank": {"payload_format": "cohere_rerank"},
            "embeddings": {"payload_format": "cohere"}
        },
        "is_active": True
    },
    {
        "provider_key": "grok",
        "name": "grok",
        "display_name": "Grok / xAI",
        "description": "xAI Grok models with high reasoning performance",
        "base_url": "https://api.x.ai/v1",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/chat/completions",
                "models": ["grok-2-latest", "grok-2-vision-1212", "grok-beta"],
                "default_model": "grok-2-latest",
                "api_key": None,
                "payload_structure": {"payload_format": "openai", "messages_key": "messages"}
            },
            {
                "name": "embedding",
                "endpoint": "/embeddings",
                "models": [
                    {"model": "v1/embeddings", "dimension": 1536}
                ],
                "default_model": "v1/embeddings",
                "api_key": None,
                "payload_structure": {"payload_format": "openai", "input_key": "input"}
            },
            {
                "name": "reranking",
                "endpoint": "/chat/completions",
                "models": ["grok-2-latest"],
                "default_model": "grok-2-latest",
                "api_key": None,
                "payload_structure": {"payload_format": "openai_chat_score"}
            }
        ],
        "chat_models": ["grok-2-latest", "grok-2-vision-1212", "grok-beta"],
        "default_chat_model": "grok-2-latest",
        "search_endpoint": "/chat/completions",
        "embedding_models": [
            {"model": "v1/embeddings", "dimension": 1536}
        ],
        "default_embedding_model": "v1/embeddings",
        "default_embedding_dimension": 1536,
        "embedding_endpoint": "/embeddings",
        "rerank_models": ["grok-2-latest"],
        "default_rerank_model": "grok-2-latest",
        "rerank_endpoint": "/chat/completions",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "Authorization",
        "capability_configs": {
            "chat": {"payload_format": "openai", "messages_key": "messages"},
            "embeddings": {"payload_format": "openai", "input_key": "input"}
        },
        "is_active": True
    },
    {
        "provider_key": "azure",
        "name": "azure",
        "display_name": "Azure OpenAI",
        "description": "Microsoft Azure OpenAI Service deployments",
        "base_url": "https://{resource}.openai.azure.com",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/openai/deployments/{model}/chat/completions?api-version=2024-02-01",
                "models": ["gpt-4o", "gpt-4o-mini", "gpt-35-turbo"],
                "default_model": "gpt-4o",
                "api_key": None,
                "payload_structure": {"payload_format": "azure_openai"}
            },
            {
                "name": "embedding",
                "endpoint": "/openai/deployments/{model}/embeddings?api-version=2024-02-01",
                "models": [
                    {"model": "text-embedding-3-small", "dimension": 1536},
                    {"model": "text-embedding-3-large", "dimension": 3072}
                ],
                "default_model": "text-embedding-3-small",
                "api_key": None,
                "payload_structure": {"payload_format": "azure_openai"}
            },
            {
                "name": "reranking",
                "endpoint": "/openai/deployments/{model}/chat/completions?api-version=2024-02-01",
                "models": ["gpt-4o-mini"],
                "default_model": "gpt-4o-mini",
                "api_key": None,
                "payload_structure": {"payload_format": "azure_openai"}
            }
        ],
        "chat_models": ["gpt-4o", "gpt-4o-mini", "gpt-35-turbo"],
        "default_chat_model": "gpt-4o",
        "search_endpoint": "/openai/deployments/{model}/chat/completions?api-version=2024-02-01",
        "embedding_models": [
            {"model": "text-embedding-3-small", "dimension": 1536},
            {"model": "text-embedding-3-large", "dimension": 3072}
        ],
        "default_embedding_model": "text-embedding-3-small",
        "default_embedding_dimension": 1536,
        "embedding_endpoint": "/openai/deployments/{model}/embeddings?api-version=2024-02-01",
        "rerank_models": ["gpt-4o-mini"],
        "default_rerank_model": "gpt-4o-mini",
        "rerank_endpoint": "/openai/deployments/{model}/chat/completions?api-version=2024-02-01",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "api-key",
        "capability_configs": {
            "chat": {"payload_format": "azure_openai"},
            "embeddings": {"payload_format": "azure_openai"},
            "rerank": {"payload_format": "azure_openai"}
        },
        "is_active": True
    },
    {
        "provider_key": "anthropic",
        "name": "anthropic",
        "display_name": "Anthropic Claude",
        "description": "Anthropic Claude AI API",
        "base_url": "https://api.anthropic.com/v1",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/messages",
                "models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
                "default_model": "claude-3-5-sonnet-20241022",
                "api_key": None,
                "payload_structure": {"payload_format": "anthropic_messages"}
            },
            {
                "name": "reranking",
                "endpoint": "/messages",
                "models": ["claude-3-5-haiku-20241022"],
                "default_model": "claude-3-5-haiku-20241022",
                "api_key": None,
                "payload_structure": {"payload_format": "anthropic_messages"}
            }
        ],
        "chat_models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
        "default_chat_model": "claude-3-5-sonnet-20241022",
        "search_endpoint": "/messages",
        "embedding_models": [],
        "default_embedding_model": None,
        "default_embedding_dimension": None,
        "embedding_endpoint": None,
        "rerank_models": ["claude-3-5-haiku-20241022"],
        "default_rerank_model": "claude-3-5-haiku-20241022",
        "rerank_endpoint": "/messages",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "x-api-key",
        "capability_configs": {
            "chat": {"payload_format": "anthropic_messages"}
        },
        "is_active": True
    },
    {
        "provider_key": "gemini",
        "name": "gemini",
        "display_name": "Google Gemini",
        "description": "Google Gemini API (gemini-2.5-flash, gemini-2.5-pro, gemini-1.5-flash, gemini-1.5-pro)",
        "base_url": "https://generativelanguage.googleapis.com",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/v1beta/models/{model}:generateContent",
                "models": ["gemini-3-pro", "gemini-3.5-flash", "gemini-3.5-pro"],
                "default_model": "gemini-3.5-flash",
                "api_key": None,
                "payload_structure": {"payload_format": "gemini"}
            },
            {
                "name": "embedding",
                "endpoint": "/v1beta/models/{model}:embedContent",
                "models": [
                    {"model": "text-embedding-004", "dimension": 768}
                ],
                "default_model": "text-embedding-004",
                "api_key": None,
                "payload_structure": {"payload_format": "gemini"}
            },
            {
                "name": "reranking",
                "endpoint": "/v1beta/models/{model}:generateContent",
                "models": ["gemini-2.5-flash", "gemini-1.5-flash"],
                "default_model": "gemini-2.5-flash",
                "api_key": None,
                "payload_structure": {"payload_format": "gemini"}
            }
        ],
        "chat_models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"],
        "default_chat_model": "gemini-2.5-flash",
        "search_endpoint": "/v1beta/models/{model}:generateContent",
        "embedding_models": [
            {"model": "text-embedding-004", "dimension": 768}
        ],
        "default_embedding_model": "text-embedding-004",
        "default_embedding_dimension": 768,
        "embedding_endpoint": "/v1beta/models/{model}:embedContent",
        "rerank_models": ["gemini-2.5-flash", "gemini-1.5-flash"],
        "default_rerank_model": "gemini-2.5-flash",
        "rerank_endpoint": "/v1beta/models/{model}:generateContent",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "x-goog-api-key",
        "capability_configs": {
            "chat": {"payload_format": "gemini"},
            "embeddings": {"payload_format": "gemini"}
        },
        "is_active": True
    }
]

async def seed_provider_presets(db: AsyncSession, force: bool = False) -> int:
    """
    Seed standard default provider presets into DB if missing or if force=True.
    Auto-populates model_types for existing rows if null.
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
        else:
            updated = False
            if force:
                for k, v in preset_data.items():
                    setattr(existing, k, v)
                updated = True
            else:
                if not existing.model_types and preset_data.get("model_types"):
                    existing.model_types = preset_data["model_types"]
                    updated = True
                if not existing.display_name and preset_data.get("display_name"):
                    existing.display_name = preset_data["display_name"]
                    updated = True
            if updated:
                count += 1

    if count > 0:
        await db.commit()
        logger.info("provider_presets_seeded", count=count)

    return count


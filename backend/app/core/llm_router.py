import os
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel

def _clean_base_url(url: str | None) -> str:
    if not url:
        return ""
    clean = str(url).rstrip("/")
    suffixes = [
        "/v1/chat/completions",
        "/chat/completions",
        "/api/chat/v1",
        "/api/chat",
        "/api/embeddings",
        "/api",
        "/v1",
    ]
    changed = True
    while changed:
        changed = False
        clean = clean.rstrip("/")
        for suffix in suffixes:
            if clean.endswith(suffix):
                clean = clean[:-len(suffix)].rstrip("/")
                changed = True
                break
    return clean


class LLMRouter:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "ollama").lower()

    async def get_llm(
        self,
        temperature=0.7,
        max_tokens=1024,
        customer_id: int | None = None,
        db=None,
        llm_config: dict | None = None,
    ):
        tenant_config = {}
        if customer_id is not None and db is not None:
            try:
                from app.models.db_models import CustomerDB, RetrievalConfigDB
                from sqlalchemy import select
                cust_stmt = select(CustomerDB).where(CustomerDB.id == customer_id)
                cust_res = await db.execute(cust_stmt)
                customer = cust_res.scalar_one_or_none()
                if customer and customer.settings:
                    tenant_config = dict(customer.settings)
                    active_config_id = customer.settings.get("active_config_id")
                    if active_config_id:
                        cfg_stmt = select(RetrievalConfigDB).where(
                            RetrievalConfigDB.id == int(active_config_id),
                            RetrievalConfigDB.customer_id == customer_id
                        )
                        cfg_res = await db.execute(cfg_stmt)
                        cfg = cfg_res.scalar_one_or_none()
                        if cfg and cfg.settings:
                            tenant_config = {**tenant_config, **cfg.settings}
            except Exception:
                pass

        if llm_config and isinstance(llm_config, dict):
            tenant_config = {**tenant_config, **llm_config}

        # Resolve config from nested sections (generation, search, llm_config) or root keys
        gen_section = tenant_config.get("generation") if isinstance(tenant_config.get("generation"), dict) else {}
        search_section = tenant_config.get("search") if isinstance(tenant_config.get("search"), dict) else {}
        llm_sec = tenant_config.get("llm_config") if isinstance(tenant_config.get("llm_config"), dict) else {}

        provider = (
            tenant_config.get("llm_provider")
            or tenant_config.get("provider")
            or gen_section.get("provider")
            or search_section.get("provider")
            or llm_sec.get("provider")
            or os.getenv("LLM_PROVIDER", "ollama")
        )
        provider = str(provider).lower()
        self.provider = provider

        raw_max_tokens = (
            tenant_config.get("max_tokens")
            or tenant_config.get("max_generation_tokens")
            or gen_section.get("max_tokens")
            or search_section.get("max_tokens")
        )
        if raw_max_tokens is not None:
            try:
                effective_max_tokens = int(raw_max_tokens)
            except (ValueError, TypeError):
                effective_max_tokens = max_tokens
        else:
            effective_max_tokens = max_tokens

        raw_temperature = (
            tenant_config.get("temperature")
            or gen_section.get("temperature")
            or search_section.get("temperature")
        )
        if raw_temperature is not None:
            try:
                effective_temperature = float(raw_temperature)
            except (ValueError, TypeError):
                effective_temperature = temperature
        else:
            effective_temperature = temperature

        resolved_model = (
            tenant_config.get("llm_model")
            or tenant_config.get("model")
            or tenant_config.get("model_name")
            or gen_section.get("model")
            or gen_section.get("model_name")
            or search_section.get("model")
            or search_section.get("model_name")
            or llm_sec.get("model")
            or llm_sec.get("model_name")
        )

        resolved_base_url = (
            tenant_config.get("llm_base_url")
            or tenant_config.get("base_url")
            or tenant_config.get("url")
            or gen_section.get("url")
            or gen_section.get("base_url")
            or search_section.get("url")
            or llm_sec.get("url")
        )

        resolved_api_key = (
            tenant_config.get("llm_api_key")
            or tenant_config.get("api_key")
            or gen_section.get("api_key")
            or search_section.get("api_key")
            or llm_sec.get("api_key")
        )

        if provider == "ollama":
            model = resolved_model or os.getenv("OLLAMA_MODEL", "qwen:0.5b")
            raw_url = resolved_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            clean_url = _clean_base_url(raw_url) or "http://localhost:11434"

            try:
                from langchain_ollama import ChatOllama
            except ImportError:
                try:
                    from langchain_community.chat_models import ChatOllama
                except ImportError:
                    raise ImportError("langchain_ollama or langchain_community package required for Ollama provider")

            return ChatOllama(
                model=model,
                base_url=clean_url,
                temperature=effective_temperature,
                num_predict=effective_max_tokens,
            )

        elif provider in ("azure", "azure_openai"):
            model = resolved_model or os.getenv("AZURE_OPENAI_MODEL", "gpt-4o")
            base_url = resolved_base_url or os.getenv("AZURE_OPENAI_ENDPOINT")
            api_key = resolved_api_key or os.getenv("AZURE_OPENAI_API_KEY")
            api_version = (
                tenant_config.get("api_version")
                or gen_section.get("api_version")
                or os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
            )
            try:
                from langchain_openai import AzureChatOpenAI
            except ImportError:
                raise ImportError("langchain_openai package required for Azure OpenAI provider")

            if not base_url:
                raise ValueError("base_url or AZURE_OPENAI_ENDPOINT required for Azure OpenAI provider")

            return AzureChatOpenAI(
                azure_endpoint=base_url,
                deployment_name=model,
                openai_api_key=api_key,
                openai_api_version=api_version,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
            )

        elif provider == "vllm":
            model = resolved_model or os.getenv("VLLM_MODEL", "default")
            raw_url = resolved_base_url or os.getenv("VLLM_BASE_URL", "http://localhost:8001")
            clean_host = _clean_base_url(raw_url) or "http://localhost:8001"
            base_url = f"{clean_host}/v1"
            api_key = resolved_api_key or os.getenv("VLLM_API_KEY", "EMPTY")
            return ChatOpenAI(
                model=model,
                base_url=base_url,
                api_key=api_key,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                streaming=True,
            )

        elif provider in ("grok", "xai"):
            model = resolved_model or os.getenv("GROK_MODEL", "grok-2-latest")
            raw_url = resolved_base_url or os.getenv("GROK_BASE_URL", "https://api.x.ai")
            clean_host = _clean_base_url(raw_url) or "https://api.x.ai"
            base_url = f"{clean_host}/v1"
            api_key = resolved_api_key or os.getenv("GROK_API_KEY", os.getenv("XAI_API_KEY", "EMPTY"))
            return ChatOpenAI(
                model=model,
                base_url=base_url,
                api_key=api_key,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                streaming=True,
            )

        elif provider in ("openai", "custom", "openai_compatible", "generic") or resolved_base_url:
            model = resolved_model or os.getenv("OPENAI_MODEL", "gpt-4o")
            raw_url = resolved_base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
            clean_host = _clean_base_url(raw_url) or "https://api.openai.com"
            base_url = f"{clean_host}/v1"
            api_key = resolved_api_key or os.getenv("OPENAI_API_KEY", "EMPTY")
            return ChatOpenAI(
                model=model,
                base_url=base_url,
                api_key=api_key,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                streaming=True,
            )

        raise ValueError(f"Provider {provider} not supported yet")
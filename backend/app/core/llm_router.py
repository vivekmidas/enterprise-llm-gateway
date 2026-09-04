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

    # ==============================================================================
    # BLOCK COMMENT: PROFILE RESOLVER INTEGRATION IN LLM ROUTER
    # Module: app/core/llm_router.py
    # Purpose:
    #   Resolves tenant's default or active profile if profile_id is not provided,
    #   or loads explicit profile when profile_id is supplied.
    # ==============================================================================
    async def get_llm(
        self,
        temperature=0.7,
        max_tokens=1024,
        customer_id: int | str | None = None,
        db=None,
        llm_config: dict | None = None,
        profile_id: str | int | None = None,
    ):
        tenant_config = {}
        if db is not None and (customer_id is not None or profile_id is not None):
            try:
                from app.core.profile_resolver import ProfileResolver
                resolver = ProfileResolver(db)
                resolved_profile = await resolver.resolve(
                    profile_id=profile_id,
                    customer_id=customer_id,
                    allow_fallback=True,
                )
                if resolved_profile:
                    gen_sec = getattr(resolved_profile, "generation", None)
                    search_sec = getattr(resolved_profile, "search", None)
                    if gen_sec:
                        tenant_config = {
                            "llm_provider": gen_sec.provider or getattr(resolved_profile, "provider", None),
                            "llm_model": gen_sec.model or getattr(resolved_profile, "model", None),
                            "llm_base_url": gen_sec.url or getattr(resolved_profile, "base_url", None),
                            "llm_api_key": gen_sec.api_key or getattr(resolved_profile, "api_key", None),
                            "temperature": gen_sec.temperature,
                            "max_tokens": gen_sec.max_tokens,
                            "generation": gen_sec.model_dump() if hasattr(gen_sec, "model_dump") else gen_sec.__dict__,
                            "search": search_sec.model_dump() if (search_sec and hasattr(search_sec, "model_dump")) else (search_sec.__dict__ if search_sec else {}),
                        }
            except Exception:
                pass

        if customer_id is not None and db is not None and not tenant_config:
            try:
                from app.models.db_models import CustomerDB, RetrievalConfigDB
                from sqlalchemy import select, or_
                cust_stmt = select(CustomerDB).where(or_(CustomerDB.id == customer_id, CustomerDB.id == str(customer_id)))
                cust_res = await db.execute(cust_stmt)
                customer = cust_res.scalar_one_or_none()
                if customer and customer.settings:
                    tenant_config = dict(customer.settings)
                    active_config_id = customer.settings.get("active_config_id")
                    if active_config_id:
                        cfg_stmt = select(RetrievalConfigDB).where(
                            RetrievalConfigDB.id == int(active_config_id),
                            RetrievalConfigDB.customer_id == str(customer_id)
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
            if not raw_url:
                raise ValueError("Ollama base_url must be specified in profile or configuration.")
            clean_url = _clean_base_url(raw_url) or "http://localhost:11434"

            try:
                from langchain_ollama import ChatOllama
            except ImportError:
                try:
                    from langchain_community.chat_models import ChatOllama
                except ImportError:
                    raise ImportError("langchain_ollama or langchain_community package required for Ollama provider")

            ollama_format = (
                tenant_config.get("format")
                or gen_section.get("format")
                or (llm_config.get("format") if isinstance(llm_config, dict) else None)
            )

            ollama_kwargs = {
                "model": model,
                "base_url": clean_url,
                "temperature": effective_temperature,
                "num_predict": effective_max_tokens,
            }
            if ollama_format:
                ollama_kwargs["format"] = ollama_format

            return ChatOllama(**ollama_kwargs)

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
            base_url = clean_host if clean_host.endswith("/v1") else f"{clean_host}/v1"
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
            base_url = clean_host if clean_host.endswith("/v1") else f"{clean_host}/v1"
            api_key = resolved_api_key or os.getenv("GROK_API_KEY", os.getenv("XAI_API_KEY", "EMPTY"))
            return ChatOpenAI(
                model=model,
                base_url=base_url,
                api_key=api_key,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                streaming=True,
            )

        elif provider in ("gemini", "google"):
            model = resolved_model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            raw_url = resolved_base_url or os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
            clean_host = str(raw_url).rstrip("/")
            if "generativelanguage.googleapis.com" in clean_host and not clean_host.endswith("v1beta/openai"):
                base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
            else:
                base_url = clean_host if (clean_host.endswith("/v1") or clean_host.endswith("/openai")) else f"{clean_host}/v1"
            api_key = resolved_api_key or os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", "EMPTY"))
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
            if not raw_url and not resolved_api_key and not os.getenv("OPENAI_API_KEY"):
                raise ValueError("OpenAI API key or base_url must be specified in profile or configuration.")
            clean_host = _clean_base_url(raw_url) or "https://api.openai.com"
            if "generativelanguage.googleapis.com" in clean_host:
                base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
            else:
                base_url = clean_host if (clean_host.endswith("/v1") or clean_host.endswith("/openai")) else f"{clean_host}/v1"
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
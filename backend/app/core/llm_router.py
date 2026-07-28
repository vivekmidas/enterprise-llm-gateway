import os
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel

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

        provider = tenant_config.get("llm_provider") or os.getenv("LLM_PROVIDER", "ollama").lower()
        provider = provider.lower()
        self.provider = provider

        raw_max_tokens = tenant_config.get("max_tokens") or tenant_config.get("max_generation_tokens")
        if raw_max_tokens is not None:
            try:
                effective_max_tokens = int(raw_max_tokens)
            except (ValueError, TypeError):
                effective_max_tokens = max_tokens
        else:
            effective_max_tokens = max_tokens

        raw_temperature = tenant_config.get("temperature")
        if raw_temperature is not None:
            try:
                effective_temperature = float(raw_temperature)
            except (ValueError, TypeError):
                effective_temperature = temperature
        else:
            effective_temperature = temperature

        if provider == "vllm":
            model = tenant_config.get("llm_model") or os.getenv("VLLM_MODEL")
            base_url = tenant_config.get("llm_base_url") or os.getenv("VLLM_BASE_URL", "http://localhost:8001/v1")
            api_key = tenant_config.get("llm_api_key") or os.getenv("VLLM_API_KEY", "")
            return ChatOpenAI(
                model=model,
                openai_api_base=base_url,
                openai_api_key=api_key,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                streaming=True,
            )
        elif provider == "ollama":
            model = tenant_config.get("llm_model") or os.getenv("OLLAMA_MODEL", "qwen:0.5b")
            base_url = tenant_config.get("llm_base_url") or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
            return ChatOpenAI(
                model=model,
                openai_api_base=f"{base_url}/v1",
                openai_api_key="ollama",
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                streaming=False,
            )
        elif provider == "openai":
            model = tenant_config.get("llm_model")
            api_key = tenant_config.get("llm_api_key") or os.getenv("OPENAI_API_KEY")
            base_url = tenant_config.get("llm_base_url") or "https://api.openai.com/v1"
            return ChatOpenAI(
                model=model,
                openai_api_base=base_url,
                openai_api_key=api_key,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                streaming=True,
            )
        raise ValueError(f"Provider {provider} not supported yet")
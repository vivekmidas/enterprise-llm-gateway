import os
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel

class LLMRouter:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "vllm").lower()

    async def get_llm(self, temperature=0.7, max_tokens=1024):
        if self.provider == "vllm":
            return ChatOpenAI(
                model=os.getenv("VLLM_MODEL"),
                openai_api_base=os.getenv("VLLM_BASE_URL", "http://localhost:8001/v1"),
                openai_api_key=os.getenv("VLLM_API_KEY", "EMPTY"),
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=True,
            )
        elif self.provider == "ollama":
            ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
            return ChatOpenAI(
                model=os.getenv("OLLAMA_MODEL", "qwen:0.5b"),
                openai_api_base=f"{ollama_base}/v1",
                openai_api_key="ollama",
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=True,
            )
        # Add more providers later
        raise ValueError(f"Provider {self.provider} not supported yet")
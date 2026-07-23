from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

class EmbeddingModelItem(BaseModel):
    model: str
    dimension: int = 768

class ProviderPresetBase(BaseModel):
    provider_key: str = Field(..., description="Unique provider identifier (e.g. ollama, vllm, openai, grok, azure, anthropic)")
    name: str = Field(..., description="Human-readable provider name")
    description: Optional[str] = None
    base_url: str = Field(..., description="Default base API URL")

    chat_models: List[str] = Field(default_factory=list, description="Supported chat generation models")
    default_chat_model: Optional[str] = None

    embedding_models: List[EmbeddingModelItem] = Field(default_factory=list, description="Supported embedding models with dimensions")
    default_embedding_model: Optional[str] = None
    default_embedding_dimension: Optional[int] = 768

    rerank_models: List[str] = Field(default_factory=list, description="Supported search/rerank models")
    default_rerank_model: Optional[str] = None

    default_temperature: float = 0.7
    default_max_tokens: int = 1024
    api_key_header: Optional[str] = None
    extra_config: Optional[Dict[str, Any]] = None
    is_active: bool = True

class ProviderPresetCreate(ProviderPresetBase):
    pass

class ProviderPresetUpdate(BaseModel):
    provider_key: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    base_url: Optional[str] = None
    chat_models: Optional[List[str]] = None
    default_chat_model: Optional[str] = None
    embedding_models: Optional[List[EmbeddingModelItem]] = None
    default_embedding_model: Optional[str] = None
    default_embedding_dimension: Optional[int] = None
    rerank_models: Optional[List[str]] = None
    default_rerank_model: Optional[str] = None
    default_temperature: Optional[float] = None
    default_max_tokens: Optional[int] = None
    api_key_header: Optional[str] = None
    extra_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class ProviderPresetResponse(ProviderPresetBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True

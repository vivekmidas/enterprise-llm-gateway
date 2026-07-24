from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict, field_validator

class EmbeddingModelItem(BaseModel):
    model: str
    dimension: int = 768

class ModelTypeSchema(BaseModel):
    name: str = Field(..., description="Capability / model type name (e.g. search, embedding, reranking)")
    endpoint: Optional[str] = Field(default=None, description="Endpoint path e.g. /responses or /chat/completions")
    models: Optional[List[Any]] = Field(default_factory=list, description="Supported model list for this capability")
    default_model: Optional[str] = Field(default=None, description="Default model for this capability")
    api_key: Optional[str] = Field(default=None, description="Capability-specific API key override")
    payload_structure: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Payload structure template & key formatting specs")

    @field_validator("models", mode="before")
    @classmethod
    def default_models_list(cls, v: Any) -> Any:
        if v is None:
            return []
        return v

class ProviderPresetBase(BaseModel):
    provider_key: str = Field(..., description="Unique provider identifier (e.g. ollama, vllm, openai, grok, azure, anthropic)")
    name: str = Field(..., description="Technical provider identifier name")
    display_name: Optional[str] = Field(default=None, description="Human-readable display name")
    description: Optional[str] = None
    base_url: str = Field(..., description="Default base API URL")

    # Structured 1-to-N model settings (search, embedding, reranking, extendable)
    model_types: Optional[List[ModelTypeSchema]] = Field(default_factory=list, description="Structured capability and model types list")

    chat_models: Optional[List[str]] = Field(default_factory=list, description="Supported chat generation models")
    default_chat_model: Optional[str] = None
    search_endpoint: Optional[str] = Field(default="/chat/completions", description="Endpoint path or relative URL for chat/completions")

    embedding_models: Optional[List[EmbeddingModelItem]] = Field(default_factory=list, description="Supported embedding models with dimensions")
    default_embedding_model: Optional[str] = None
    default_embedding_dimension: Optional[int] = 768
    embedding_endpoint: Optional[str] = Field(default="/embeddings", description="Endpoint path or relative URL for embeddings")

    rerank_models: Optional[List[str]] = Field(default_factory=list, description="Supported search/rerank models")
    default_rerank_model: Optional[str] = None
    rerank_endpoint: Optional[str] = Field(default="/rerank", description="Endpoint path or relative URL for reranking")

    default_temperature: float = 0.7
    default_max_tokens: int = 1024
    api_key_header: Optional[str] = None
    capability_configs: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Capability-specific payload templates & attributes")
    extra_config: Optional[Dict[str, Any]] = None
    is_active: bool = True

    @field_validator("model_types", "chat_models", "embedding_models", "rerank_models", mode="before")
    @classmethod
    def default_empty_list(cls, v: Any) -> Any:
        if v is None:
            return []
        return v


class ProviderPresetCreate(ProviderPresetBase):
    pass

class ProviderPresetUpdate(BaseModel):
    provider_key: Optional[str] = None
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    base_url: Optional[str] = None
    model_types: Optional[List[ModelTypeSchema]] = None
    chat_models: Optional[List[str]] = None
    default_chat_model: Optional[str] = None
    search_endpoint: Optional[str] = None
    embedding_models: Optional[List[EmbeddingModelItem]] = None
    default_embedding_model: Optional[str] = None
    default_embedding_dimension: Optional[int] = None
    embedding_endpoint: Optional[str] = None
    rerank_models: Optional[List[str]] = None
    default_rerank_model: Optional[str] = None
    rerank_endpoint: Optional[str] = None
    default_temperature: Optional[float] = None
    default_max_tokens: Optional[int] = None
    api_key_header: Optional[str] = None
    capability_configs: Optional[Dict[str, Any]] = None
    extra_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class ProviderPresetResponse(ProviderPresetBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


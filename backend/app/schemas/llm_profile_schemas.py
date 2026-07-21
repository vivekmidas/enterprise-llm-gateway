"""
LLM Profile API schemas.

LLMProfileSettings is now a typed alias for ProfileSettings (four sections).
The old flat schema is preserved here only for backward-compat imports.
"""
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from app.schemas.profile_sections import ProfileSettings


# ---------------------------------------------------------------------------
# Public create / update / response schemas
# ---------------------------------------------------------------------------

class LLMProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None)
    is_default: bool = Field(default=False)
    settings: Union[ProfileSettings, Dict[str, Any]] = Field(default_factory=ProfileSettings)


class LLMProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None)
    is_default: Optional[bool] = Field(default=None)
    settings: Optional[Union[ProfileSettings, Dict[str, Any]]] = Field(default=None)


class LLMProfileResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    customer_id: int
    created_by: int
    is_default: bool
    settings: Dict[str, Any]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Playground schemas
# ---------------------------------------------------------------------------

class PlaygroundTestRequest(BaseModel):
    profile_id: Optional[int] = Field(default=None)
    knowledge_base_ids: List[int] = Field(default_factory=list)
    query: str = Field(min_length=1)
    chat_history: Optional[List[Dict[str, Any]]] = Field(default=None)

    # Transient per-request overrides (scratchpad only)
    embedding: Optional[Dict[str, Any]] = Field(default=None)
    search: Optional[Dict[str, Any]] = Field(default=None)
    reranking: Optional[Dict[str, Any]] = Field(default=None)
    generation: Optional[Dict[str, Any]] = Field(default=None)


class PlaygroundTestResponse(BaseModel):
    answer: str
    full_compiled_prompt: Optional[str] = Field(default=None)
    retrieved_chunks: List[Dict[str, Any]] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Backward-compat alias — old code that imports LLMProfileSettings still works
# ---------------------------------------------------------------------------
LLMProfileSettings = ProfileSettings

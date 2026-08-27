from typing import Any, Dict, Optional, List

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    domain_id: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    domain_id: Optional[str] = None
    status: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    domain_id: Optional[str] = None
    status: str
    customer_id: str
    created_by: str
    settings: Optional[Dict[str, Any]]
    created_at: str
    updated_at: str
    llm_profile_warning: Optional[str] = None  # Populated when no LLM profile configured for tenant
    model_config = {"from_attributes": True}


class KnowledgeDocumentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: str = "upload"
    source_uri: Optional[str] = None
    mime_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeDocumentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[Any]] = None
    status: Optional[str] = None


class KnowledgeDocumentResponse(BaseModel):
    id: str
    knowledge_base_id: str
    customer_id: str
    created_by: str

    name: str
    source_type: str
    source_uri: Optional[str]
    mime_type: Optional[str]

    metadata_json: Optional[Dict[str, Any]]
    tags: Optional[List[Dict[str, Any]]] = None

    status: str
    error_message: Optional[str]

    created_at: str
    updated_at: str

    file_path: Optional[str]
    file_size: Optional[int]
    checksum: Optional[str]
    chunk_count: int

    job_progress: Optional[int] = None
    job_message: Optional[str] = None
    model_config = {"from_attributes": True}

class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1)
    knowledge_base_ids: list[str]
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    enable_reranking: Optional[bool] = None
    rerank_url: Optional[str] = Field(default=None)
    rerank_model: Optional[str] = Field(default=None)
    rerank_limit: Optional[int] = Field(default=None, ge=1, le=100)
    approach: Optional[str] = None
    enable_rrf: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None

class Citation(BaseModel):
    document_id: str
    document_name: str
    chunk_index: int


class RetrievalResult(BaseModel):
    rank: int
    chunk_id: str
    document_id: str
    document_name: str
    knowledge_base_id: str
    content: str

    score: float
    vector_score: float | None = None

    metadata: dict[str, Any] | None = None
    citation: Citation


class ResponseGenerationRequest(BaseModel):
    query: str = Field(min_length=1)
    context: Any  # Should map to RetrievalContext
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_generation_tokens: int = Field(default=1024, ge=1)
    customer_id: Optional[str] = None
    llm_config: Optional[Dict[str, Any]] = None
    llm_config_id: Optional[str] = None


class RAGRequest(BaseModel):
    query: str = Field(min_length=1)
    knowledge_base_ids: list[str]
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_context_tokens: int = Field(default=6000, ge=500)
    enable_reranking: Optional[bool] = None
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
class DocumentViewsResponse(BaseModel):
    document_id: str
    document_name: str
    status: str
    created_at: str
    views: Dict[str, Any]
    comparison_report: Optional[Dict[str, Any]] = None
    entity_provenance: Optional[List[Dict[str, Any]]] = None
    model_config = {"from_attributes": True}


class DocumentViewsUpdate(BaseModel):
    normalized_text: Optional[str] = None
    structured_json: Optional[Dict[str, Any]] = None



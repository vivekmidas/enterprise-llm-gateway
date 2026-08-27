import uuid
from sqlalchemy import Column, String, JSON, Integer, Boolean, Float, ForeignKey, Text, DateTime, Enum
from app.core.database import Base
from datetime import datetime
from sqlalchemy.sql import func
from app.jobs.enums import JobStatus
from app.jobs.enums import JobType
from app.jobs.enums import EntityType

"""
===============================================================================
BLOCK COMMENT: DATABASE MODELS (MYSQL & UUIDv4 COMPATIBLE)
Module: backend/app/models/db_models.py
Description:
    Updated primary keys from Integer to String(36) UUIDv4 generator.
    Explicit string lengths added to indexed columns for MySQL key limits.
===============================================================================
"""

def generate_uuid() -> str:
    return str(uuid.uuid4())

# BLOCK COMMENT: STREAMLINED 3-TIER RBAC MODELS (xx:yy:zzz FORMAT)
# Modified: CustomerDB (allowed_domains), PermissionDB (submodule), RoutePermissionDB (module, submodule, label)

class CustomerDB(Base):
    __tablename__ = "customers"
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), unique=True, index=True)
    domain = Column(String(255), unique=True, index=True, nullable=True)  # Useful for auto-assigning users via SSO
    status = Column(String(50), default="active")  # active, suspended
    icon = Column(String(500), nullable=True)
    color_schema = Column(String(100), nullable=True)
    custom_plugins_enabled = Column(Boolean, default=False)
    plugin_storage_path = Column(String(500), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(String(500), nullable=True)
    contact_person = Column(String(255), nullable=True)
    dateadded = Column(String(100), default=lambda: datetime.utcnow().isoformat())
    dateupdated = Column(String(100), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())
    document_types = Column(JSON, nullable=True, default=list)
    settings = Column(JSON, nullable=True, default=dict)
    allowed_domains = Column(JSON, nullable=True, default=list)  # Allowed top-level modules e.g. ["legal"]


class UserDB(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    username = Column(String(255), unique=True, index=True)
    email_id = Column(String(255), unique=True, index=True)
    password = Column(String(255), nullable=False)  # Store bcrypt hashed password
    name = Column(String(255), nullable=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True)
    role_id = Column(String(36), ForeignKey("roles.id"), nullable=True)
    status = Column(String(50), default="active")  # active, deactivated, suspended
    role = Column(String(50), default="user")     # legacy: admin, user, system_admin
    created_at = Column(String(100), default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String(100), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())


class RoleDB(Base):
    __tablename__ = "roles"
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True)
    role_name = Column(String(100), nullable=False)
    role_type = Column(String(50), nullable=False)  # system_admin, tenant_admin, para_legal, legal_analyst, tenant_user, custom
    description = Column(Text, nullable=True)
    is_system_preset = Column(Boolean, default=False)
    created_at = Column(String(100), default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String(100), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())


# BLOCK COMMENT: CANONICAL MODULE SOT & 3-TIER RBAC MODELS
class ModuleDB(Base):
    __tablename__ = "modules"
    id = Column(String(50), primary_key=True, index=True)  # e.g., admin_knowledge, user_mgmt, etc.
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True)
    module = Column(String(50), nullable=False, index=True) # admin, knowledge, workflows, legal, etc.
    submodule = Column(String(50), nullable=True, index=True) # knowledge, users, profiles, etc.
    label = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    route_patterns = Column(JSON, nullable=False) # e.g. ["/admin/knowledge", "/knowledge"]
    icon = Column(String(50), nullable=True) # Lucide icon name
    display_order = Column(Integer, default=0)
    created_at = Column(String(100), default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String(100), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())


# ==============================================================================
# BLOCK COMMENT: ACTION CAPABILITY & API ENDPOINT RBAC MODELS
# Adds api_path and http_methods to PermissionDB and http_method to RoutePermissionDB
# for dynamic UI-configurable API verb/path authorization.
# ==============================================================================
class PermissionDB(Base):
    __tablename__ = "permissions"
    id = Column(String(100), primary_key=True, index=True)  # e.g., admin:knowledge:view, admin:knowledge:create
    module_id = Column(String(50), ForeignKey("modules.id", ondelete="CASCADE"), nullable=True, index=True)
    module = Column(String(50), nullable=False, index=True) # legal, knowledge, workflows, nodes, admin
    submodule = Column(String(50), nullable=True, index=True) # case_management, research, user_management, etc.
    action = Column(String(50), nullable=True, index=True) # view, create, edit, delete, ingest, query, execute
    is_route_guard = Column(Boolean, default=False) # True if this action grants navigation & entry to the route
    target_layer = Column(String(20), default="both")       # ui, api, both
    api_path = Column(String(255), nullable=True)           # e.g., /api/knowledge/bases, /api/legal/bookmarks
    http_methods = Column(JSON, nullable=True)             # e.g., ["GET", "POST", "DELETE"]
    label = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)


class RolePermissionDB(Base):
    __tablename__ = "role_permissions"
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    role_id = Column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id = Column(String(100), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True)
    allowed_methods = Column(JSON, nullable=True) # e.g., ["GET", "POST"] method-level granular authorization


class RoutePermissionDB(Base):
    __tablename__ = "route_permissions"
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True)
    pattern = Column(String(150), nullable=False, index=True) # UI route or API path pattern
    http_method = Column(String(20), default="*")             # "GET", "POST", "PUT", "DELETE", or "*"
    permission_id = Column(String(100), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    module = Column(String(50), nullable=True, index=True)
    submodule = Column(String(50), nullable=True, index=True)
    label = Column(String(150), nullable=True)
    description = Column(Text, nullable=True)
# END BLOCK: ACTION CAPABILITY & API ENDPOINT RBAC MODELS



class CategoryDB(Base):
    __tablename__ = "categories"
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    group = Column(String(255), unique=True, index=True)
    icon = Column(String(255), nullable=True)
    color = Column(String(100), nullable=True)
    label = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

class NodeDB(Base):
    __tablename__ = "nodes"
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), unique=True, index=True)
    label = Column(String(255))
    node_type = Column(String(50), default="default")  # trigger, tool, or default
    description = Column(Text)
    version = Column(String(50))
    category = Column(String(255))
    group = Column(String(255))
    icon = Column(String(255))
    color = Column(String(100))
    badge = Column(String(100), nullable=True)
    sub_label = Column(String(255), nullable=True)
    user_properties = Column(JSON)
    system_properties = Column(JSON)
    input_contract=Column(JSON)
    output_contract=Column(JSON)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)


class CustomerNodeDB(Base):
    __tablename__ = "customer_nodes"
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    node_name = Column(String(255), nullable=False, index=True)
    properties = Column(JSON, nullable=True)
    is_enabled = Column(Boolean, default=True)
    input_contract = Column(JSON, nullable=True)
    output_contract = Column(JSON, nullable=True)
    label = Column(String(255), nullable=True)
    updated_at = Column(String(100), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())


class WorkflowNodeDB(Base):
    __tablename__ = "workflow_nodes"
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    workflow_id = Column(String(255), nullable=False)  # Foreign key to WorkflowDB.id
    agent_node_id = Column(String(255))  # Trigger Node ID from the workflow definition
    description = Column(Text)
    agent_name = Column(String(255))
    updated_at = Column(String(100))
    
class WorkflowDB(Base):
    __tablename__ = "workflows"

    id = Column(String(255), primary_key=True, index=True)
    name = Column(String(255), index=True)
    description = Column(Text, nullable=True)
    version = Column(Integer)

    edges = Column(Text, nullable=True)
    category = Column(String(255), nullable=True)
    nodes_structure = Column(Text, nullable=True)
    definition = Column(JSON, nullable=True)
    updated_at = Column(String(100))
    is_enabled = Column(Boolean, default=True)
    is_runnable = Column(Boolean, default=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    user_id = Column(String(36), nullable=True, index=True) # User ID of the creator
    

class WorkflowNodePropertyDB(Base):
    __tablename__ = "workflow_node_properties"
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    workflow_id = Column(String(255), nullable=False, index=True)
    agent_node_id = Column(String(255), nullable=False, index=True)
    agent_name = Column(String(255), nullable=True, index=True)
    properties = Column(JSON)
    label = Column(String(255), nullable=True)
    input_contract = Column(JSON, nullable=True)
    output_contract = Column(JSON, nullable=True)
    allow_node_testing = Column(Boolean, nullable=True)

    
class CredentialDB(Base):
    __tablename__ = "credentials"
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), unique=True, index=True)
    type = Column(String(100), nullable=False)
    config = Column(JSON, nullable=False)
    auth_data = Column(JSON, nullable=True)
    created_at = Column(String(100), default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String(100), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())

class OAuthProviderDB(Base):
    __tablename__ = "oauth_providers"
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), unique=True, index=True) # Machine key, e.g., 'okta', 'linkedin'
    label = Column(String(255)) # UI display name, e.g., 'Okta'
    description = Column(Text, nullable=True)
    auth_url = Column(String(500), nullable=True)
    token_url = Column(String(500), nullable=True)
    default_scopes = Column(String(500), nullable=True)
    callback_url = Column(String(500), nullable=True)
    icon = Column(String(500), nullable=True)

class AuditLogDB(Base):
    __tablename__ = "audit_logs"
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    action = Column(String(255), nullable=False, index=True)
    resource_type = Column(String(255), nullable=False, index=True)
    resource_id = Column(String(255), nullable=True, index=True)
    status = Column(String(255), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    actor_role = Column(String(255), nullable=True, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    details = Column(JSON, nullable=True)
    created_at = Column(String(100), default=lambda: datetime.utcnow().isoformat(), index=True)


class JobDB(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    job_type = Column(Enum(JobType), nullable=False, index=True)
    entity_type = Column(Enum(EntityType), nullable=True, index=True)
    entity_id = Column(String(36), nullable=True, index=True)
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.QUEUED, index=True)
    progress = Column(Integer, nullable=False, default=0)
    message = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    job_metadata = Column("metadata", JSON, nullable=False, default=dict)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __init__(self, **kwargs):
        metadata = kwargs.pop("metadata", None)
        super().__init__(**kwargs)
        self.job_metadata = metadata or {}
                        
class DomainSchemaDB(Base):
    __tablename__ = "domain_schemas"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    domain_key = Column(String(100), nullable=False, index=True)
    scope = Column(String(50), default="TENANT", index=True)  # SYSTEM or TENANT
    customer_id = Column(
        String(36), ForeignKey("customers.id"), nullable=True, index=True
    )
    schema_json = Column(JSON, nullable=True)
    system_prompt = Column(Text, nullable=True)
    user_prompt = Column(Text, nullable=True)
    created_by = Column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )

    created_at = Column(
        String(100), default=lambda: datetime.utcnow().isoformat()
    )
    updated_at = Column(
        String(100),
        default=lambda: datetime.utcnow().isoformat(),
        onupdate=lambda: datetime.utcnow().isoformat(),
    )


class KnowledgeBaseDB(Base):
    __tablename__ = "knowledge_bases"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="active", index=True)
    customer_id = Column(
        String(36), ForeignKey("customers.id"), nullable=False, index=True
    )
    domain_id = Column(
        String(36), ForeignKey("domain_schemas.id"), nullable=True, index=True
    )
    created_by = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    settings = Column(JSON, nullable=True)

    created_at = Column(
        String(100), default=lambda: datetime.utcnow().isoformat()
    )
    updated_at = Column(
        String(100),
        default=lambda: datetime.utcnow().isoformat(),
        onupdate=lambda: datetime.utcnow().isoformat(),
    )

class KnowledgeCollectionDB(Base):
    __tablename__ = "knowledge_collections"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    knowledge_base_id = Column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    customer_id = Column(
        String(36),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding_model = Column(String(255), nullable=True)
    vector_dimension = Column(Integer, nullable=True)
    distance_metric = Column(String(50), default="COSINE")
    status = Column(String(50), default="active", index=True)

    created_at = Column(
        String(100), default=lambda: datetime.utcnow().isoformat()
    )
    updated_at = Column(
        String(100),
        default=lambda: datetime.utcnow().isoformat(),
        onupdate=lambda: datetime.utcnow().isoformat(),
    )


class KnowledgeDocumentDB(Base):
    __tablename__ = "knowledge_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    knowledge_base_id = Column(
        String(36),
        ForeignKey("knowledge_bases.id"),
        nullable=False,
        index=True,
    )
    customer_id = Column(
        String(36), ForeignKey("customers.id"), nullable=False, index=True
    )
    created_by = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    collection_id = Column(
        String(36),
        ForeignKey("knowledge_collections.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    name = Column(String(255), nullable=False)
    source_type = Column(String(100), default="upload")
    source_uri = Column(String(500), nullable=True)
    mime_type = Column(String(100), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    extracted_json = Column(JSON, nullable=True)

    status = Column(
        String(50),
        default="pending",
        index=True,
    )

    error_message = Column(Text, nullable=True)

    created_at = Column(
        String(100), default=lambda: datetime.utcnow().isoformat()
    )
    updated_at = Column(
        String(100),
        default=lambda: datetime.utcnow().isoformat(),
        onupdate=lambda: datetime.utcnow().isoformat(),
    )
    file_path = Column(String(500), nullable=True)
    file_size = Column(Integer, nullable=True)
    checksum = Column(String(255), nullable=True, index=True)
    chunk_count = Column(Integer, default=0)
    collection_name = Column(String(255), nullable=True, index=True)
    embedding_model = Column(String(255), nullable=True)
    vector_dimension = Column(Integer, nullable=True)
    distance_metric = Column(String(50), default="COSINE")


class KnowledgeChunkDB(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    document_id = Column(
        String(36),
        ForeignKey("knowledge_documents.id"),
        nullable=False,
        index=True,
    )
    knowledge_base_id = Column(
        String(36),
        ForeignKey("knowledge_bases.id"),
        nullable=False,
        index=True,
    )
    customer_id = Column(
        String(36),
        ForeignKey("customers.id"),
        nullable=False,
        index=True,
    )

    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=True)

    created_at = Column(
        String(100),
        default=lambda: datetime.utcnow().isoformat(),
    )


# ==============================================================================
# BLOCK COMMENT: NORMALIZED DOCUMENT TAGS & PRE-COMPUTED PHONETIC INDEX TABLE
# Module: app/models/db_models.py
# Purpose:
#   Stores granular, normalized, and pre-computed phonetic tags extracted at ingestion
#   (Coram, Section, Statute, Court, Timeline Dates, Disposition, Concepts)
# ==============================================================================
# BLOCK COMMENT: DYNAMIC AUTO-POPULATING CANONICAL TAXONOMY TERMS TABLE
# Module: app/models/db_models.py
# Purpose:
#   Central Master Taxonomy table storing canonical terms (Courts, Statutes, Sections,
#   Judges, Dispositions, Concepts) and pre-computed phonetics (Soundex, Metaphone, NYSIIS)
#   with alias mapping and usage counting.
# ==============================================================================

class TaxonomyTermDB(Base):
    __tablename__ = "taxonomy_terms"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    customer_id = Column(
        String(36), nullable=True, index=True
    )  # Null = Global term, String = Tenant-specific custom term

    category = Column(String(50), nullable=False, index=True)        # 'court', 'judge', 'statute', 'section', 'disposition', 'concept', 'timeline'
    canonical_name = Column(String(255), nullable=False)             # 'High Court of Jharkhand, Ranchi', 'Justice H.C. Mishra'
    canonical_normalized = Column(String(255), nullable=False, index=True) # Lowercase stripped

    aliases_json = Column(JSON, nullable=True)                       # ["dhc", "delhi hc", "high court delhi"]
    code = Column(String(50), nullable=True)                         # Optional official code: '7_26', 'IPC_307'

    soundex_code = Column(String(50), nullable=True, index=True)
    metaphone_code = Column(String(100), nullable=True, index=True)
    nysiis_code = Column(String(100), nullable=True)

    usage_count = Column(Integer, default=1, index=True)             # Frequency of appearance
    is_auto_discovered = Column(Boolean, default=True)               # Discovered by AI vs predefined
    is_verified = Column(Boolean, default=False)                     # Admin verified

    created_at = Column(
        String(100), default=lambda: datetime.utcnow().isoformat()
    )
    updated_at = Column(
        String(100),
        default=lambda: datetime.utcnow().isoformat(),
        onupdate=lambda: datetime.utcnow().isoformat(),
    )


# ==============================================================================
# BLOCK COMMENT: CENTRALIZED DOCUMENT TAG MAPPING (JUNCTION TABLE)
# Module: app/models/db_models.py
# Purpose:
#   3NF normalized mapping between KnowledgeDocumentDB and central TaxonomyTermDB.
#   Lightweight foreign key mapping enabling instant sub-millisecond joins and zero duplication.
# ==============================================================================

class DocumentTagMappingDB(Base):
    __tablename__ = "document_tag_mappings"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    customer_id = Column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id = Column(
        String(36), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    knowledge_base_id = Column(
        String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag_id = Column(
        String(36), ForeignKey("taxonomy_terms.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tag_type = Column(String(50), nullable=False, index=True)       # 'judge', 'court', 'statute', 'section', 'year', 'disposition', 'trial_date', 'judgment_date', 'incident_date', 'concept'
    tag_value = Column(String(255), nullable=True)                  # Display copy of canonical name

    is_inferred = Column(Boolean, default=True)                      # True = AI extracted, False = User manual tag
    created_at = Column(
        String(100), default=lambda: datetime.utcnow().isoformat()
    )


# Backward-compatible alias
DocumentTagDB = DocumentTagMappingDB


class LLMProfileDB(Base):
    __tablename__ = "llm_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    is_default = Column(Boolean, default=False, index=True)
    customer_id = Column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    settings = Column(JSON, nullable=False)

    created_at = Column(
        String(100), default=lambda: datetime.utcnow().isoformat()
    )
    updated_at = Column(
        String(100),
        default=lambda: datetime.utcnow().isoformat(),
        onupdate=lambda: datetime.utcnow().isoformat(),
    )


class RetrievalConfigDB(Base):
    __tablename__ = "retrieval_configs"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    customer_id = Column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    settings = Column(JSON, nullable=False)

    created_at = Column(
        String(100), default=lambda: datetime.utcnow().isoformat()
    )
    updated_at = Column(
        String(100),
        default=lambda: datetime.utcnow().isoformat(),
        onupdate=lambda: datetime.utcnow().isoformat(),
    )


class ProviderPresetDB(Base):
    __tablename__ = "provider_presets"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    provider_key = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(String(1000), nullable=True)
    base_url = Column(String(500), nullable=False)

    # Structured capability / model settings hierarchy
    model_types = Column(JSON, nullable=True, default=list)

    chat_models = Column(JSON, nullable=True, default=list)
    default_chat_model = Column(String(255), nullable=True)
    search_endpoint = Column(String(500), nullable=True, default="/chat/completions")

    embedding_models = Column(JSON, nullable=True, default=list)
    default_embedding_model = Column(String(255), nullable=True)
    default_embedding_dimension = Column(Integer, nullable=True, default=768)
    embedding_endpoint = Column(String(500), nullable=True, default="/embeddings")

    rerank_models = Column(JSON, nullable=True, default=list)
    default_rerank_model = Column(String(255), nullable=True)
    rerank_endpoint = Column(String(500), nullable=True, default="/rerank")

    default_temperature = Column(Float, default=0.7)
    default_max_tokens = Column(Integer, default=1024)
    api_key_header = Column(String(100), nullable=True)
    capability_configs = Column(JSON, nullable=True, default=dict)
    extra_config = Column(JSON, nullable=True, default=dict)

    is_active = Column(Boolean, default=True, index=True)

    created_at = Column(
        String(100), default=lambda: datetime.utcnow().isoformat()
    )
    updated_at = Column(
        String(100),
        default=lambda: datetime.utcnow().isoformat(),
        onupdate=lambda: datetime.utcnow().isoformat(),
    )


"""
===============================================================================
BLOCK COMMENT: EKP V3 ENTERPRISE KNOWLEDGE PLATFORM MODELS
Module: backend/app/models/db_models.py
Author: EKP Architecture Team
Description:
    SQLAlchemy database models for EKP V3 multi-tenant domain intelligence,
    2-phase ingestion, CDM storage, paragraph provenance, MACD entities,
    and normalized multi-stage approval workflows.
===============================================================================
"""

class EKPDomainDB(Base):
    __tablename__ = "ekp_domains"

    id = Column(String(64), primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    version = Column(String(32), nullable=False, default="1.0")
    schema_definition = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EKPDocumentDB(Base):
    __tablename__ = "ekp_documents"

    id = Column(String(64), primary_key=True, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    knowledge_base_id = Column(String(64), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    mime_type = Column(String(64), nullable=False)
    domain_id = Column(String(64), ForeignKey("ekp_domains.id"), nullable=True, index=True)
    llm_profile_id = Column(String(36), ForeignKey("llm_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    cdm_payload = Column(JSON, nullable=False)

    # Automated System Processing Stage
    processing_stage = Column(String(32), default="UPLOADED", nullable=False, index=True)
    processing_error = Column(Text, nullable=True)

    # Human Multi-Stage Approval Workflow (Normalized: joins with ekp_approval_stages via current_stage_order)
    current_stage_order = Column(Integer, default=1, nullable=False)
    approval_status = Column(String(32), default="PENDING", nullable=False, index=True)

    min_confidence = Column(Float, default=1.0)
    current_review_version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EKPJobDB(Base):
    __tablename__ = "ekp_jobs"

    id = Column(String(64), primary_key=True, index=True)
    document_id = Column(String(64), ForeignKey("ekp_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    job_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="QUEUED", index=True)
    retry_count = Column(Integer, default=0)
    worker_id = Column(String(128), nullable=True)
    error_log = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EKPParagraphDB(Base):
    __tablename__ = "ekp_paragraphs"

    id = Column(String(128), primary_key=True, index=True) # span_id
    document_id = Column(String(64), ForeignKey("ekp_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    paragraph_number = Column(Integer, nullable=False)
    text_content = Column(Text, nullable=False)
    bounding_box = Column(JSON, nullable=True)


class EKPEntityDB(Base):
    __tablename__ = "ekp_entities"

    id = Column(String(64), primary_key=True, index=True)
    document_id = Column(String(64), ForeignKey("ekp_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    domain_id = Column(String(64), ForeignKey("ekp_domains.id"), nullable=True, index=True)
    entity_type = Column(String(64), nullable=False, index=True)
    entity_key = Column(String(128), nullable=False, index=True)
    value = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=False, default=1.0)
    basis = Column(String(32), nullable=False, default="FACT") # FACT, INFERENCE, UNKNOWN
    provenance_page = Column(Integer, nullable=True)
    provenance_paragraph = Column(Integer, nullable=True)
    provenance_span_id = Column(String(128), ForeignKey("ekp_paragraphs.id", ondelete="SET NULL"), nullable=True, index=True)
    review_required = Column(Boolean, default=False, index=True)
    version = Column(Integer, default=1, nullable=False)
    review_version = Column(Integer, default=1, nullable=False)
    is_deleted = Column(Boolean, default=False, index=True)
    last_modified_by = Column(String(128), default="SYSTEM_EXTRACTOR")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EKPRelationshipDB(Base):
    __tablename__ = "ekp_relationships"

    id = Column(String(64), primary_key=True, index=True)
    document_id = Column(String(64), ForeignKey("ekp_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    source_entity_id = Column(String(64), ForeignKey("ekp_entities.id", ondelete="CASCADE"), nullable=False, index=True)
    target_entity_id = Column(String(64), ForeignKey("ekp_entities.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type = Column(String(64), nullable=False, index=True)
    confidence = Column(Float, nullable=False, default=1.0)
    provenance_span_id = Column(String(128), ForeignKey("ekp_paragraphs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EKPApprovalStageDB(Base):
    __tablename__ = "ekp_approval_stages"

    id = Column(String(64), primary_key=True, index=True)
    domain_id = Column(String(64), ForeignKey("ekp_domains.id"), nullable=False, index=True)
    stage_order = Column(Integer, nullable=False)
    stage_name = Column(String(128), nullable=False)
    required_role = Column(String(64), nullable=False)
    is_mandatory = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EKPApprovalHistoryDB(Base):
    __tablename__ = "ekp_approval_history"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    document_id = Column(String(64), ForeignKey("ekp_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    review_version = Column(Integer, nullable=False)
    stage_order = Column(Integer, nullable=False)
    stage_name = Column(String(128), nullable=False)
    reviewer_id = Column(String(128), nullable=False)
    reviewer_role = Column(String(64), nullable=False)
    decision = Column(String(32), nullable=False) # APPROVE, REJECT, REQUEST_CHANGES
    comments = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EKPDocumentReviewDB(Base):
    __tablename__ = "ekp_document_reviews"

    id = Column(String(64), primary_key=True, index=True)
    document_id = Column(String(64), ForeignKey("ekp_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    review_version = Column(Integer, nullable=False)
    reviewer_id = Column(String(128), nullable=False)
    reviewer_type = Column(String(32), nullable=False, default="HUMAN")
    approval_status = Column(String(32), nullable=False)
    changes_summary = Column(JSON, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EKPAuditLogDB(Base):
    __tablename__ = "ekp_audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    document_id = Column(String(64), ForeignKey("ekp_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(String(64), nullable=True)
    action = Column(String(64), nullable=False)
    performed_by = Column(String(128), nullable=False)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SavedQueryDB(Base):
    __tablename__ = "saved_queries"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    customer_id = Column(String(36), nullable=True, index=True)
    domain = Column(String(50), default="legal", index=True)
    title = Column(String(255), nullable=False)
    query_text = Column(Text, nullable=True)
    filters_json = Column(JSON, nullable=True, default=dict)
    is_public = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KnowledgeAuditLogDB(Base):
    __tablename__ = "knowledge_audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    customer_id = Column(String(36), nullable=True, index=True)
    domain = Column(String(50), nullable=True, index=True)
    role = Column(String(50), nullable=True)
    action = Column(String(64), nullable=False, index=True)  # SEARCH, INGEST, SYNTHESIZE, EXPORT_BRIEF, SAVE_QUERY
    query_text = Column(Text, nullable=True)
    results_count = Column(Integer, default=0)
    details_json = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# Backward-compatible alias
LegalAuditLogDB = KnowledgeAuditLogDB




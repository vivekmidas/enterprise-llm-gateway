from sqlalchemy import Column, String, JSON, Integer, Boolean
from sqlalchemy import Column, String, JSON, Integer, Boolean, ForeignKey
from app.core.database import Base
from datetime import datetime


class CustomerDB(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    domain = Column(String, unique=True, index=True, nullable=True)  # Useful for auto-assigning users via SSO
    status = Column(String, default="active")  # active, suspended
    icon = Column(String, nullable=True)
    color_schema = Column(String, nullable=True)
    dateadded = Column(String, default=lambda: datetime.utcnow().isoformat())
    dateupdated = Column(String, default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())


class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email_id = Column(String, unique=True, index=True)
    password = Column(String, nullable=False)  # Store bcrypt hashed password
    name = Column(String, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    status = Column(String, default="active")  # active, deactivated, suspended
    role = Column(String, default="user")     # admin, user
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String, default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())


class CategoryDB(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    group = Column(String, unique=True, index=True)
    icon = Column(String, nullable=True)
    color = Column(String, nullable=True)
    label = Column(String, nullable=True)
    description = Column(String, nullable=True)

class NodeDB(Base):
    __tablename__ = "nodes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    label = Column(String)
    node_type = Column(String, default="default")  # trigger, tool, or default
    description = Column(String)
    version = Column(String)
    category = Column(String)
    group = Column(String)
    icon = Column(String)
    color = Column(String)
    badge = Column(String, nullable=True)
    sub_label = Column(String, nullable=True)
    user_properties = Column(JSON)
    system_properties = Column(JSON)
    input_contract=Column(JSON)
    output_contract=Column(JSON)


class CustomerNodeDB(Base):
    __tablename__ = "customer_nodes"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    node_name = Column(String, nullable=False, index=True)
    properties = Column(JSON, nullable=True)
    is_enabled = Column(Boolean, default=True)
    updated_at = Column(String, default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())


class WorkflowNodeDB(Base):
    __tablename__ = "workflow_nodes"
    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(String, nullable=False)  # Foreign key to WorkflowDB.id
    agent_node_id = Column(String)  # Trigger Node ID from the workflow definition
    description = Column(String)
    agent_name = Column(String)
    updated_at = Column(String)
    
class WorkflowDB(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    version = Column(Integer)

    edges = Column(String, nullable=True)
    category = Column(String, nullable=True)
    nodes_structure = Column(String, nullable=True)
    definition = Column(JSON, nullable=True)
    updated_at = Column(String)
    is_enabled = Column(Boolean, default=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    user_id = Column(String, nullable=True, index=True) # User ID of the creator
    

class WorkflowNodePropertyDB(Base):
    __tablename__ = "workflow_node_properties"
    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(String, nullable=False, index=True)
    agent_node_id = Column(String, nullable=False, index=True)
    agent_name = Column(String, nullable=True, index=True)
    properties = Column(JSON)
    
class CredentialDB(Base):
    __tablename__ = "credentials"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    type = Column(String, nullable=False)
    config = Column(JSON, nullable=False)
    auth_data = Column(JSON, nullable=True)
    created_at = Column(String, default=datetime.utcnow)
    updated_at = Column(String, default=datetime.utcnow, onupdate=datetime.utcnow)

class OAuthProviderDB(Base):
    __tablename__ = "oauth_providers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True) # Machine key, e.g., 'okta', 'linkedin'
    label = Column(String) # UI display name, e.g., 'Okta'
    description = Column(String, nullable=True)
    auth_url = Column(String, nullable=False)
    token_url = Column(String, nullable=False)
    default_scopes = Column(String, nullable=True)
    callback_url = Column(String, nullable=False)
    icon = Column(String, nullable=True)
                        

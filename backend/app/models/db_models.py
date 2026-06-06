from sqlalchemy import Column, String, JSON, Integer, Boolean
from app.core.database import Base

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
    node_type = Column(String, default="default")  # trigger, tool, or default
    name = Column(String, unique=True, index=True)
    label = Column(String)
    description = Column(String)
    version = Column(String)
    category = Column(String)
    group = Column(String)
    icon = Column(String)
    color = Column(String)
    badge = Column(String, nullable=True)
    sub_label = Column(String, nullable=True)
    property_schema = Column(JSON)
    properties = Column(JSON)
    
class WorkflowDB(Base):
    __tablename__ = "workflows"
    id = Column(String, primary_key=True, index=True)  # UUID string
    name = Column(String)
    description = Column(String)
    version = Column(Integer)
    category = Column(String)
    definition = Column(JSON)  # Single source of truth for the workflow graph (nodes, edges, and their properties)
    updated_at = Column(String)
    is_enabled = Column(Boolean, default=True)
    
class WorkflowNodeDB(Base):
    __tablename__ = "workflow_nodes"
    id = Column(Integer, primary_key=True, index=True)
    agent_name = Column(String)  # For easier querying of nodes by name without joining with NodeDB
    workflow_id = Column(String, nullable=False)  # Foreign key to WorkflowDB.id
    agent_node_id = Column(String)  # Trigger Node ID from the workflow definition
    updated_at = Column(String)
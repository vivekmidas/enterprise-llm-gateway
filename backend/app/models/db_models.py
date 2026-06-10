from sqlalchemy import Column, String, JSON, Integer, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from app.core.database import Base
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()
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
    property_schema = Column(JSON)
    properties = Column(JSON)
    
class WorkflowNodeDB(Base):
    __tablename__ = "workflow_nodes"
    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(String, nullable=False)  # Foreign key to WorkflowDB.id
    agent_node_id = Column(String)  # Trigger Node ID from the workflow definition
    description = Column(String)
    agent_name = Column(String)
    updated_at = Column(String)
    properties = Column(JSON)
    
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
    

class WorkflowNodePropertyDB(Base):
    __tablename__ = "workflow_node_properties"
    id = Column(Integer, primary_key=True, index=True)
    workflow_node_id = Column(Integer, ForeignKey("workflow_nodes.id"))
    key = Column(String, index=True)
    value = Column(String)
    

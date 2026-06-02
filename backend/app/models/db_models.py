from sqlalchemy import Column, String, JSON, Integer
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
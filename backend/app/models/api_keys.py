# app/models/api_key.py
import secrets

from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

class APIKey(Base):
    __tablename__ = "api_keys"
    key = Column(String, primary_key=True, default=lambda: secrets.token_urlsafe(32))
    name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
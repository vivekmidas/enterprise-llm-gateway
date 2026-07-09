from pydantic import BaseModel, Field
from typing import Optional


class User (BaseModel):
    id: str
    role: str
    email: str
    customer_id: Optional[int] = None
    domain: Optional[str] = None
    name: Optional[str] = None

    
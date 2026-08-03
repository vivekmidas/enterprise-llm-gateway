from typing import Optional, List
from pydantic import BaseModel, ConfigDict

class CategoryBase(BaseModel):
    group: str
    icon: Optional[str] = None
    label: str = None
    color: Optional[str] = None
    description: Optional[str] = None # tooltip or detailed description for the category

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    group: Optional[str] = None
    label: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None

class CategoryResponse(CategoryBase):
    id: str
    model_config = ConfigDict(from_attributes=True)

class CategoryListResponse(BaseModel):
    categories: List[CategoryResponse]
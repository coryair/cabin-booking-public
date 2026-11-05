from pydantic import BaseModel, Field
from typing import Optional


class DocumentCreate(BaseModel):
    title: str = Field(..., description="Document title")
    url: str = Field(..., description="Document URL")
    description: Optional[str] = Field(None, description="Brief description of the document")


class DocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Document title")
    url: Optional[str] = Field(None, description="Document URL")
    description: Optional[str] = Field(None, description="Brief description of the document")
    sort_order: Optional[int] = Field(None, description="Display order (lower = first)")


class DocumentResponse(BaseModel):
    id: int
    title: str
    url: str
    description: Optional[str] = None
    sort_order: int = 0
    created_at: Optional[str] = None

    class Config:
        from_attributes = True

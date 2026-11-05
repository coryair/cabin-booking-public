from pydantic import BaseModel, Field
from typing import Optional


class CabinBase(BaseModel):
    cabin_id: str = Field(..., description="Unique cabin identifier", example="pine")
    cabin_name: str = Field(..., description="Display name for the cabin", example="Pine")
    description: Optional[str] = Field(None, description="Cabin description and amenities", example="Lakeside cabin with 3 bedrooms")
    max_guests: int = Field(10, description="Maximum number of guests allowed", example=10)


class CabinCreate(CabinBase):
    pass


class CabinUpdate(BaseModel):
    cabin_name: Optional[str] = Field(None, description="Display name for the cabin", example="Pine")
    description: Optional[str] = Field(None, description="Cabin description and amenities", example="Lakeside cabin with 3 bedrooms")
    max_guests: Optional[int] = Field(None, description="Maximum number of guests allowed", example=10)


class CabinResponse(CabinBase):
    id: int = Field(..., description="Cabin database ID", example=1)
    created_at: Optional[str] = Field(None, description="Cabin record creation timestamp", example="2024-01-01T00:00:00")

    class Config:
        from_attributes = True

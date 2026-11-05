from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class Season(str, Enum):
    offseason = "offseason"
    onseason = "onseason"


class RateBase(BaseModel):
    season: Season = Field(..., description="Season type (offseason or onseason)", example="onseason")
    nightly_rate: float = Field(..., description="Rate per night in dollars", example=150.00)
    daily_rate: float = Field(..., description="Rate per day in dollars", example=100.00)
    effective_date: str = Field(..., description="Date when this rate becomes effective (YYYY-MM-DD)", example="2024-06-01")


class RateCreate(RateBase):
    pass


class RateUpdate(BaseModel):
    season: Optional[Season] = Field(None, description="Season type (offseason or onseason)", example="onseason")
    nightly_rate: Optional[float] = Field(None, description="Rate per night in dollars", example=150.00)
    daily_rate: Optional[float] = Field(None, description="Rate per day in dollars", example=100.00)
    effective_date: Optional[str] = Field(None, description="Date when this rate becomes effective (YYYY-MM-DD)", example="2024-06-01")


class RateResponse(RateBase):
    id: int = Field(..., description="Rate database ID", example=1)

    class Config:
        from_attributes = True

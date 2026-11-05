from pydantic import BaseModel, Field
from typing import Optional


class BookingRoundCreate(BaseModel):
    round_number: int
    start_date: str
    end_date: str
    window_days: int
    max_reservations: int
    max_nights: Optional[int] = None
    priority_order: str = "priority"


class BookingRoundResponse(BookingRoundCreate):
    id: int
    season_id: int

    class Config:
        from_attributes = True


class BookingSeasonCreate(BaseModel):
    year: int = Field(..., example=2026)
    prime_season_start: str = Field(..., example="2026-06-01")
    prime_season_end: str = Field(..., example="2026-09-30")
    open_season_start: str = Field(..., example="2026-05-20")
    open_season_end: str = Field(..., example="2026-09-07")
    season_max_nights: int = Field(18)
    processing_fee_pct: float = Field(0.04)
    guest_fee_per_day: float = Field(10.0)
    rounds: list[BookingRoundCreate] = Field(default_factory=list)


class BookingSeasonUpdate(BaseModel):
    prime_season_start: Optional[str] = None
    prime_season_end: Optional[str] = None
    open_season_start: Optional[str] = None
    open_season_end: Optional[str] = None
    season_max_nights: Optional[int] = None
    processing_fee_pct: Optional[float] = None
    guest_fee_per_day: Optional[float] = None
    rounds: Optional[list[BookingRoundCreate]] = None


class BookingSeasonResponse(BaseModel):
    id: int
    year: int
    prime_season_start: str
    prime_season_end: str
    open_season_start: str
    open_season_end: str
    season_max_nights: int
    processing_fee_pct: float
    guest_fee_per_day: float = 10.0
    rounds: list[BookingRoundResponse] = []

    class Config:
        from_attributes = True


class BookingStatusResponse(BaseModel):
    current_round: str
    current_round_display: str
    can_book: bool
    reason: Optional[str] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    nights_used: int = 0
    nights_remaining: int = 0
    season_max_nights: int = 0
    round_reservations: int = 0
    round_max_reservations: int = 0
    round_nights: int = 0
    round_max_nights: Optional[int] = None
    now_booking_share_name: Optional[str] = None
    priority: Optional[int] = None
    total_shares: Optional[int] = None
    next_phase: Optional[str] = None
    next_phase_date: Optional[str] = None
    prime_season_start: Optional[str] = None
    prime_season_end: Optional[str] = None


class BookingEligibilityResponse(BaseModel):
    eligible: bool
    reason: Optional[str] = None
    booking_round: Optional[str] = None
    current_round: Optional[str] = None


class CostPreviewResponse(BaseModel):
    base_cost: float
    processing_fee: float
    total: float
    nightly_rate: float
    daily_rate: float = 0.0
    nights: int
    cabin_count: int
    season_type: str
    fee_pct: float
    is_day_use: bool = False
    guest_fee: float = 0.0
    guest_fee_rate: float = 0.0
    guest_count: int = 0
    guest_nights_total: int = 0

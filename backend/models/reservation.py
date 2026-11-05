from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Literal
from enum import Enum
import json


class ReservationStatus(str, Enum):
    reserved = "reserved"
    unpaid = "unpaid"
    paid = "paid"
    cancelled = "cancelled"
    refunded = "refunded"


class ReservationCreate(BaseModel):
    share: str = Field(..., description="Share ID of the shareholder making the reservation", example="spruce")
    guest_count: int = Field(0, ge=0, description="Number of non-family guests", example=4)
    guest_nights: Optional[list[int]] = Field(
        None, description="Per-guest nights list, e.g. [1,2] for Guest 1 = 1 night, Guest 2 = 2 nights"
    )
    start_date: str = Field(..., description="Check-in date (YYYY-MM-DD)", example="2024-07-01")
    end_date: str = Field(..., description="Check-out date (YYYY-MM-DD)", example="2024-07-05")
    cabins: list[str] = Field(..., description="Cabin name to reserve (1 cabin allowed)", example=["pine"])
    is_day_use: bool = Field(False, description="Day-use (picnic) reservation vs overnight")

    @field_validator("cabins")
    @classmethod
    def validate_cabins(cls, v):
        if not v or len(v) == 0:
            raise ValueError("At least one cabin must be selected")
        if len(v) > 1:
            raise ValueError("Only one cabin can be booked per reservation")
        return v

    @field_validator("guest_nights")
    @classmethod
    def validate_guest_nights(cls, v):
        if v is None:
            return v
        for i, n in enumerate(v):
            if int(n) < 1:
                raise ValueError(f"Guest {i + 1} nights must be at least 1")
        return [int(n) for n in v]


class ReservationSelfUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guest_count: Optional[int] = Field(None, ge=0, description="Number of guests for the reservation", example=6)
    guest_nights: Optional[list[int]] = Field(None, description="Per-guest nights list")

    @field_validator("guest_nights")
    @classmethod
    def validate_guest_nights(cls, v):
        if v is None:
            return v
        for i, n in enumerate(v):
            if int(n) < 1:
                raise ValueError(f"Guest {i + 1} nights must be at least 1")
        return [int(n) for n in v]


class ReservationAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guest_count: Optional[int] = Field(None, ge=0, description="Number of guests for the reservation", example=6)
    guest_nights: Optional[list[int]] = Field(None, description="Per-guest nights list")
    start_date: Optional[str] = Field(None, description="Check-in date (YYYY-MM-DD)", example="2024-07-02")
    end_date: Optional[str] = Field(None, description="Check-out date (YYYY-MM-DD)", example="2024-07-06")
    cabins: Optional[list[str]] = Field(None, description="Cabin name to reserve (1 cabin allowed)", example=["pine"])
    status: Optional[ReservationStatus] = Field(None, description="Reservation payment status", example="paid")

    @field_validator("cabins")
    @classmethod
    def validate_cabins(cls, v):
        if v is None:
            return v
        if not v or len(v) == 0:
            raise ValueError("At least one cabin must be selected")
        if len(v) > 1:
            raise ValueError("Only one cabin can be booked per reservation")
        return v

    @field_validator("guest_nights")
    @classmethod
    def validate_guest_nights(cls, v):
        if v is None:
            return v
        for i, n in enumerate(v):
            if int(n) < 1:
                raise ValueError(f"Guest {i + 1} nights must be at least 1")
        return [int(n) for n in v]


class ReservationResponse(BaseModel):
    id: int = Field(..., description="Reservation database ID", example=1)
    share: str = Field(..., description="Share ID of the shareholder who made the reservation", example="spruce")
    share_name: Optional[str] = Field(None, description="Display name for the share (e.g., 'Spruce', 'Demo Six')")
    booked_by_shareholder_id: Optional[int] = Field(
        None,
        description="Shareholder ID of the user who placed the reservation",
    )
    booked_by_shareholder_name: Optional[str] = Field(
        None,
        description="Full name of the shareholder who placed the reservation",
    )
    guest_count: int = Field(..., description="Number of guests", example=4)
    guest_nights: Optional[list[int]] = Field(None, description="Per-guest nights list")
    start_date: str = Field(..., description="Check-in date (YYYY-MM-DD)", example="2024-07-01")
    end_date: str = Field(..., description="Check-out date (YYYY-MM-DD)", example="2024-07-05")
    cabins: list[str] = Field(..., description="Reserved cabin names", example=["pine"])
    cost: float = Field(..., description="Total reservation cost in dollars", example=450.00)
    booking_round: Optional[str] = Field(None, description="Booking round (round_1, round_2, round_3, open, offseason, admin)")
    base_cost: Optional[float] = Field(None, description="Cost before processing fee")
    processing_fee: Optional[float] = Field(None, description="Processing fee amount (4%)")
    is_day_use: bool = Field(False, description="Day-use (picnic) reservation vs overnight")
    guest_fee: Optional[float] = Field(None, description="Total guest fee for non-family guests")
    status: str = Field(..., description="Reservation status", example="reserved")
    stripe_checkout_session_id: Optional[str] = Field(None, description="Stripe Checkout session ID")
    stripe_payment_intent_id: Optional[str] = Field(None, description="Stripe payment intent ID")
    created_at: Optional[str] = Field(None, description="Reservation creation timestamp", example="2024-06-01T10:30:00")
    cancelled_at: Optional[str] = Field(None, description="Cancellation timestamp")
    refund_amount: Optional[float] = Field(None, description="Dollar amount refunded")
    refunded_at: Optional[str] = Field(None, description="Stripe refund timestamp")
    stripe_refund_id: Optional[str] = Field(None, description="Comma-separated Stripe refund object IDs")
    cancellation_reason: Optional[str] = Field(None, description="Reason for cancellation")

    class Config:
        from_attributes = True

    @field_validator("cabins", mode="before")
    @classmethod
    def parse_cabins(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("guest_nights", mode="before")
    @classmethod
    def parse_guest_nights(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v


class AvailabilityResponse(BaseModel):
    available: bool = Field(..., description="Whether the requested dates/cabins are available", example=True)
    cabins: dict[str, bool] = Field(..., description="Availability status per cabin", example={"pine": True, "cedar": False})
    conflicts: list[ReservationResponse] = Field(default=[], description="List of conflicting reservations if not available")


class RefundPreviewResponse(BaseModel):
    eligible: bool = Field(..., description="Whether the reservation is eligible for a refund")
    cancellation_eligible: bool = Field(True, description="Whether the reservation can be cancelled at all")
    days_until_checkin: int = Field(..., description="Days between today and check-in date")
    refund_amount: float = Field(..., description="Amount that would be refunded")
    requested_refund_amount: float = Field(0.0, description="Requested refund before fee retention")
    processing_fee_kept: float = Field(..., description="Processing fee retained (non-refundable)")
    policy_fee_target: float = Field(0.0, description="Booking fee target retained by policy")
    status: str = Field(..., description="Current reservation status")
    reason: str = Field(..., description="Explanation of eligibility")
    admin_override: bool = Field(False, description="Admin bypassed the cancellation window")
    override_required: bool = Field(False, description="Whether an admin must explicitly override the refund notice policy")


class AdminRefundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    override_policy: bool = Field(
        False,
        description="Explicitly refund inside the cancellation notice window",
    )


class CancelReservationResponse(BaseModel):
    status: str = Field(..., description="New reservation status after cancellation")
    refund_issued: bool = Field(False, description="Whether a Stripe refund was issued")
    refund_amount: Optional[float] = Field(None, description="Amount refunded")
    message: str = Field(..., description="Human-readable result message")


class GuestAdjustmentRequest(BaseModel):
    guest_nights: list[int] = Field(default_factory=list, description="Updated per-guest nights list")

    @field_validator("guest_nights")
    @classmethod
    def validate_guest_nights(cls, v):
        for i, n in enumerate(v):
            if int(n) < 1:
                raise ValueError(f"Guest {i + 1} nights must be at least 1")
        return [int(n) for n in v]


class GuestAdjustmentPreviewResponse(BaseModel):
    reservation_id: int
    allowed: bool
    reason: Optional[str] = None
    action: Literal["collect", "refund", "apply", "none"]
    edit_deadline: Optional[str] = None
    current_guest_nights: list[int] = Field(default_factory=list)
    updated_guest_nights: list[int] = Field(default_factory=list)
    current_guest_count: int = 0
    updated_guest_count: int = 0
    current_guest_nights_total: int = 0
    updated_guest_nights_total: int = 0
    current_guest_fee: float = 0.0
    updated_guest_fee: float = 0.0
    current_processing_fee: float = 0.0
    updated_processing_fee: float = 0.0
    current_total: float = 0.0
    updated_total: float = 0.0
    delta_guest_fee: float = 0.0
    delta_processing_fee: float = 0.0
    delta_total: float = 0.0
    charge_amount: float = 0.0
    refund_amount: float = 0.0
    requested_refund_amount: float = 0.0
    processing_fee_retained: float = 0.0
    processing_fee_retained_total: float = 0.0
    policy_fee_target: float = 0.0
    reservation_status: str


class GuestAdjustmentCheckoutResponse(BaseModel):
    reservation_id: int
    adjustment_id: int
    checkout_url: str


class GuestAdjustmentApplyResponse(BaseModel):
    reservation: ReservationResponse
    action: Literal["apply", "refund", "none"]
    adjustment_id: Optional[int] = None
    refund_issued: bool = False
    refund_amount: Optional[float] = None
    message: str


class GuestAdjustmentReconcileRequest(BaseModel):
    adjustment_id: int


class GuestAdjustmentReconcileResponse(BaseModel):
    status: Literal["paid", "pending", "applied", "failed", "cancelled", "refunded"]
    adjustment_id: int
    reservation_id: int

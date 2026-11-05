from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class AllowedShareResponse(BaseModel):
    share_id: str = Field(..., description="Share ID", example="spruce")
    share_name: str = Field(..., description="Display name for the share", example="Spruce")
    priority: int = Field(..., description="Booking priority for the share", example=1)


class ShareholderBase(BaseModel):
    share: str = Field(..., description="Share ID (e.g., 'spruce', 'willow')", example="spruce")
    first_name: str = Field(..., description="Shareholder's first name", example="John")
    last_name: str = Field(..., description="Shareholder's last name", example="Doe")
    email: EmailStr = Field(..., description="Shareholder's email address", example="john.doe@example.com")
    phone_number: Optional[str] = Field(None, description="Shareholder's phone number")


class ShareholderCreate(ShareholderBase):
    password: str = Field(..., description="Account password")
    is_viewer: bool = Field(False, description="Viewer-only flag")
    is_analytics: bool = Field(False, description="Analytics-only admin panel flag")


class ShareholderUpdate(BaseModel):
    share: Optional[str] = Field(None, description="Share ID (e.g., 'spruce', 'willow')", example="spruce")
    first_name: Optional[str] = Field(None, description="Shareholder's first name", example="Jane")
    last_name: Optional[str] = Field(None, description="Shareholder's last name", example="Smith")
    email: Optional[EmailStr] = Field(None, description="Shareholder's email address", example="jane.smith@example.com")
    phone_number: Optional[str] = Field(None, description="Shareholder's phone number")
    password: Optional[str] = Field(None, description="New account password")
    is_viewer: Optional[bool] = Field(None, description="Viewer-only flag (superadmin-only)")
    is_analytics: Optional[bool] = Field(None, description="Analytics-only admin panel flag (superadmin-only)")
    is_admin: Optional[bool] = Field(None, description="Admin flag (superadmin-only)")
    is_superadmin: Optional[bool] = Field(None, description="Superadmin flag (superadmin-only)")
    additional_shares: Optional[list[str]] = Field(
        None,
        description="Additional share IDs this shareholder can access (superadmin-only)",
    )
    cancellation_availability_emails_enabled: Optional[bool] = Field(
        None,
        description="Whether cancellation-availability alerts are enabled for this account",
    )


class ShareholderResponse(ShareholderBase):
    id: int = Field(..., description="Database record ID", example=1)
    share_name: Optional[str] = Field(None, description="Display name for the share (e.g., 'Spruce', 'Demo Six')")
    priority: int = Field(..., description="Booking priority from share (lower = higher priority)", example=1)
    last_booked: Optional[str] = Field(None, description="Date of last booking (YYYY-MM-DD)", example="2024-06-15")
    is_viewer: bool = Field(False, description="Whether shareholder has viewer-only access")
    is_analytics: bool = Field(False, description="Whether shareholder has analytics-only admin panel access")
    is_admin: bool = Field(False, description="Whether shareholder has admin access")
    is_superadmin: bool = Field(False, description="Whether shareholder has superadmin access")
    allowed_shares: list[AllowedShareResponse] = Field(
        default_factory=list,
        description="All shares this shareholder is allowed to act on, including primary share",
    )
    can_access_multiple_shares: bool = Field(
        False,
        description="Whether the shareholder can access more than one share",
    )
    tour_seen: bool = Field(False, description="Whether the shareholder has completed the onboarding tour")
    cancellation_availability_emails_enabled: bool = Field(
        True,
        description="Whether cancellation-availability alerts are enabled for this account",
    )
    created_at: Optional[str] = Field(None, description="Account creation timestamp", example="2024-01-01T00:00:00")

    class Config:
        from_attributes = True


class ShareholderLogin(BaseModel):
    email: EmailStr = Field(..., description="Shareholder's email address", example="john.doe@example.com")
    password: str = Field(..., description="Account password")


class AuthCheckResponse(BaseModel):
    authenticated: bool = Field(..., description="Whether the user is authenticated", example=True)
    shareholder: Optional[ShareholderResponse] = Field(None, description="Shareholder details if authenticated")


class MagicLinkRequest(BaseModel):
    email: EmailStr = Field(..., description="Email address to send magic link to")


class MagicLinkVerify(BaseModel):
    token: str = Field(..., description="Magic link token")


class InvitationCreate(BaseModel):
    email: EmailStr = Field(..., description="Email address to invite")
    share: str = Field(..., description="Share ID to assign")
    first_name: str = Field(..., description="Invitee's first name")
    last_name: str = Field(..., description="Invitee's last name")
    phone_number: Optional[str] = Field(None, description="Invitee's phone number")
    is_viewer: bool = Field(False, description="Whether the invite should create a viewer-only account")


class InvitationAccept(BaseModel):
    token: str = Field(..., description="Invitation token from the magic link")
    first_name: str = Field(..., description="New shareholder's first name")
    last_name: str = Field(..., description="New shareholder's last name")
    email: EmailStr = Field(..., description="Email address (must match invitation)")
    password: Optional[str] = Field(None, description="Account password (optional, use magic link if omitted)")
    phone_number: Optional[str] = Field(None, description="Phone number")


class InvitationResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    phone_number: Optional[str] = None
    share: str
    share_name: Optional[str] = None
    is_viewer: bool = False
    expires_at: str
    used_at: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True

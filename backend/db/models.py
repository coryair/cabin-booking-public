from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class Share(Base):
    __tablename__ = "shares"

    share_id = Column(String, primary_key=True)  # e.g., "spruce", "willow"
    share_name = Column(String, nullable=False)  # e.g., "Spruce", "Demo Six"
    priority = Column(Integer, nullable=False, default=0)  # Lower = higher priority

    # Relationships
    shareholders = relationship("Shareholder", back_populates="share_rel")
    reservations = relationship("Reservation", back_populates="share_rel")
    shareholder_accesses = relationship("ShareholderShareAccess", back_populates="share_rel", cascade="all, delete-orphan")


class Cabin(Base):
    __tablename__ = "cabins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cabin_id = Column(String, unique=True, nullable=False)  # e.g., "pine", "cedar"
    cabin_name = Column(String, nullable=False)  # e.g., "Pine", "Cedar"
    description = Column(Text)
    max_guests = Column(Integer, nullable=False, default=10)
    created_at = Column(String, server_default=func.now())


class Shareholder(Base):
    __tablename__ = "shareholders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    share = Column(String, ForeignKey("shares.share_id", ondelete="CASCADE"), nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone_number = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)
    last_booked = Column(String)
    is_viewer = Column(Integer, nullable=False, default=0)
    is_analytics = Column(Integer, nullable=False, default=0)
    is_admin = Column(Integer, nullable=False, default=0)
    is_superadmin = Column(Integer, nullable=False, default=0)
    tour_seen = Column(Integer, nullable=False, default=0)
    cancellation_availability_emails_enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(String, server_default=func.now())

    # Relationships
    share_rel = relationship("Share", back_populates="shareholders")
    additional_share_accesses = relationship(
        "ShareholderShareAccess",
        back_populates="shareholder_rel",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sessions = relationship("Session", back_populates="shareholder_rel", cascade="all, delete-orphan", passive_deletes=True)


class ShareholderShareAccess(Base):
    __tablename__ = "shareholder_share_access"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shareholder_id = Column(Integer, ForeignKey("shareholders.id", ondelete="CASCADE"), nullable=False, index=True)
    share_id = Column(String, ForeignKey("shares.share_id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(String, server_default=func.now())

    shareholder_rel = relationship("Shareholder", back_populates="additional_share_accesses")
    share_rel = relationship("Share", back_populates="shareholder_accesses")

    __table_args__ = (
        UniqueConstraint("shareholder_id", "share_id", name="uq_shareholder_share_access"),
    )


class Rate(Base):
    __tablename__ = "rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    season = Column(String, nullable=False)
    nightly_rate = Column(Float, nullable=False)
    daily_rate = Column(Float, nullable=False)
    effective_date = Column(String, nullable=False)

    __table_args__ = (
        CheckConstraint("season IN ('offseason', 'onseason')", name="check_season"),
    )


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    share = Column(String, ForeignKey("shares.share_id", ondelete="CASCADE"), nullable=False, index=True)
    booked_by_shareholder_id = Column(Integer, ForeignKey("shareholders.id", ondelete="SET NULL"), nullable=True)
    guest_count = Column(Integer, nullable=False)
    guest_nights_json = Column(Text, nullable=True)  # JSON array of guest nights, e.g. [1,2]
    start_date = Column(String, nullable=False)
    end_date = Column(String, nullable=False)
    cabins = Column(Text, nullable=False)  # JSON array: ["pine"] or ["cedar"]
    cost = Column(Float, nullable=False)
    booking_round = Column(String, nullable=True)  # round_1, round_2, round_3, open, offseason, admin
    base_cost = Column(Float, nullable=True)
    processing_fee = Column(Float, nullable=True)
    is_day_use = Column(Integer, nullable=False, default=0)
    guest_fee = Column(Float, nullable=True)
    guest_fee_refunded = Column(Float, nullable=True, default=0.0)
    status = Column(String, nullable=False, default="reserved")
    stripe_checkout_session_id = Column(String, nullable=True)
    stripe_payment_intent_id = Column(String, nullable=True)
    created_at = Column(String, server_default=func.now())
    cancelled_at = Column(String, nullable=True)
    refund_amount = Column(Float, nullable=True)
    refunded_at = Column(String, nullable=True)
    stripe_refund_id = Column(String, nullable=True)
    cancellation_reason = Column(String, nullable=True)

    # Relationship
    share_rel = relationship("Share", back_populates="reservations")
    booked_by_shareholder_rel = relationship("Shareholder", foreign_keys=[booked_by_shareholder_id])

    __table_args__ = (
        CheckConstraint("guest_count >= 0", name="check_guest_count"),
        CheckConstraint("end_date >= start_date", name="check_dates"),
        CheckConstraint("status IN ('reserved', 'unpaid', 'paid', 'cancelled', 'refunded')", name="check_status"),
    )


class ReservationGuestAdjustment(Base):
    __tablename__ = "reservation_guest_adjustments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False, index=True)
    before_guest_nights_json = Column(Text, nullable=False)
    after_guest_nights_json = Column(Text, nullable=False)
    before_guest_fee = Column(Float, nullable=False, default=0.0)
    after_guest_fee = Column(Float, nullable=False, default=0.0)
    before_processing_fee = Column(Float, nullable=False, default=0.0)
    after_processing_fee = Column(Float, nullable=False, default=0.0)
    before_total = Column(Float, nullable=False, default=0.0)
    after_total = Column(Float, nullable=False, default=0.0)
    delta_guest_fee = Column(Float, nullable=False, default=0.0)
    delta_processing_fee = Column(Float, nullable=False, default=0.0)
    delta_total = Column(Float, nullable=False, default=0.0)
    action = Column(String, nullable=False)  # collect | refund | apply | none
    status = Column(String, nullable=False, default="pending")  # pending | applied | paid | refunded | failed | cancelled
    stripe_checkout_session_id = Column(String, nullable=True)
    stripe_payment_intent_id = Column(String, nullable=True)
    stripe_refund_id = Column(String, nullable=True)
    created_by_shareholder_id = Column(Integer, ForeignKey("shareholders.id", ondelete="SET NULL"), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(String, server_default=func.now())
    updated_at = Column(String, nullable=True)

    reservation_rel = relationship("Reservation")

    __table_args__ = (
        CheckConstraint(
            "action IN ('collect', 'refund', 'apply', 'none')",
            name="check_guest_adjustment_action",
        ),
        CheckConstraint(
            "status IN ('pending', 'applied', 'paid', 'refunded', 'failed', 'cancelled')",
            name="check_guest_adjustment_status",
        ),
    )


class BookingSeason(Base):
    __tablename__ = "booking_seasons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, unique=True, nullable=False)
    prime_season_start = Column(String, nullable=False)  # YYYY-MM-DD
    prime_season_end = Column(String, nullable=False)

    # Open season & limits
    open_season_start = Column(String, nullable=False)
    open_season_end = Column(String, nullable=False)
    season_max_nights = Column(Integer, nullable=False, default=18)
    processing_fee_pct = Column(Float, nullable=False, default=0.04)
    guest_fee_per_day = Column(Float, nullable=False, default=10.0)

    # Rounds
    rounds = relationship(
        "BookingRound", back_populates="season",
        order_by="BookingRound.round_number",
        cascade="all, delete-orphan", lazy="joined"
    )


class BookingRound(Base):
    __tablename__ = "booking_rounds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, ForeignKey("booking_seasons.id", ondelete="CASCADE"), nullable=False)
    round_number = Column(Integer, nullable=False)
    start_date = Column(String, nullable=False)  # YYYY-MM-DD
    end_date = Column(String, nullable=False)
    window_days = Column(Integer, nullable=False)
    max_reservations = Column(Integer, nullable=False)
    max_nights = Column(Integer, nullable=True)  # null = no per-round cap
    priority_order = Column(String, nullable=False, default="priority")  # "priority" or "reverse"

    season = relationship("BookingSeason", back_populates="rounds")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    shareholder_id = Column(Integer, ForeignKey("shareholders.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(String, server_default=func.now())
    expires_at = Column(String, nullable=False)

    # Relationship
    shareholder_rel = relationship("Shareholder", back_populates="sessions")


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(String, primary_key=True)  # UUID
    email = Column(String, nullable=False, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    token = Column(String, unique=True, nullable=False, index=True)
    share = Column(String, ForeignKey("shares.share_id", ondelete="CASCADE"), nullable=False)
    is_viewer = Column(Integer, nullable=False, default=0)
    expires_at = Column(String, nullable=False)
    used_at = Column(String, nullable=True)
    created_at = Column(String, server_default=func.now())

    # Relationship
    share_rel = relationship("Share")


class InvitationReminderLog(Base):
    __tablename__ = "invitation_reminder_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invitation_id = Column(String, ForeignKey("invitations.id", ondelete="CASCADE"), nullable=False, index=True)
    reminder_date = Column(String, nullable=False)
    sent_at = Column(String, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("invitation_id", "reminder_date", name="uq_invitation_reminder_invitation_date"),
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)


class LoginToken(Base):
    __tablename__ = "login_tokens"

    id = Column(String, primary_key=True)  # UUID
    email = Column(String, nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    shareholder_id = Column(Integer, ForeignKey("shareholders.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(String, nullable=False)
    used_at = Column(String, nullable=True)
    created_at = Column(String, server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    url = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(String, server_default=func.now())


class ReminderLog(Base):
    __tablename__ = "reminder_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    share_id = Column(String, ForeignKey("shares.share_id", ondelete="CASCADE"), nullable=False)
    round_name = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    sent_at = Column(String, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("share_id", "round_name", "year", name="uq_reminder_share_round_year"),
    )

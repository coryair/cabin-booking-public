from .auth import router as auth_router
from .shareholders import router as shareholders_router
from .reservations import router as reservations_router
from .rates import router as rates_router
from .cabins import router as cabins_router
from .booking_seasons import router as booking_seasons_router
from .time_travel import router as time_travel_router
from .invitations import router as invitations_router
from .cron import router as cron_router
from .documents import router as documents_router
from .checkout import router as checkout_router
from .availability_alerts import router as availability_alerts_router

__all__ = [
    "auth_router",
    "shareholders_router",
    "reservations_router",
    "rates_router",
    "cabins_router",
    "booking_seasons_router",
    "time_travel_router",
    "invitations_router",
    "cron_router",
    "documents_router",
    "checkout_router",
    "availability_alerts_router",
]

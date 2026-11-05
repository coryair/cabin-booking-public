from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import cors_origins
from db.database import engine
from db.models import AppSetting, Document, InvitationReminderLog, ReminderLog, ShareholderShareAccess
from routers import (
    auth_router,
    shareholders_router,
    reservations_router,
    rates_router,
    cabins_router,
    booking_seasons_router,
    time_travel_router,
    invitations_router,
    cron_router,
    documents_router,
    checkout_router,
    availability_alerts_router,
)

app = FastAPI(
    title="Cabin Booking API",
    description="Backend API for Cabin Booking reservation system",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(shareholders_router)
app.include_router(reservations_router)
app.include_router(rates_router)
app.include_router(cabins_router)
app.include_router(booking_seasons_router)
app.include_router(time_travel_router)
app.include_router(invitations_router)
app.include_router(cron_router)
app.include_router(documents_router)
app.include_router(checkout_router)
app.include_router(availability_alerts_router)

# Ensure tables exist (safe no-op if already present)
AppSetting.__table__.create(bind=engine, checkfirst=True)
ReminderLog.__table__.create(bind=engine, checkfirst=True)
InvitationReminderLog.__table__.create(bind=engine, checkfirst=True)
Document.__table__.create(bind=engine, checkfirst=True)
ShareholderShareAccess.__table__.create(bind=engine, checkfirst=True)


@app.get("/")
def root():
    return {"message": "Cabin Booking API", "version": "1.0.0"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}

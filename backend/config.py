import json
import os
import secrets
import tempfile

from pydantic_settings import BaseSettings
from pathlib import Path


_project_root = Path(__file__).parent.parent
_default_secret = secrets.token_hex(32)
_default_sqlite = f"sqlite:///{_project_root / 'data' / 'cabins.db'}"


def _normalize_database_url(url: str) -> str:
    normalized = (url or "").strip().strip('"').strip("'")
    # Normalize Postgres DSNs and default to psycopg (v3) driver.
    if normalized.startswith("postgres://"):
        normalized = normalized.replace("postgres://", "postgresql+psycopg://", 1)
    elif normalized.startswith("postgresql://") and "+" not in normalized.split("://", 1)[0]:
        normalized = normalized.replace("postgresql://", "postgresql+psycopg://", 1)
    return normalized


def _resolve_database_url() -> str:
    url = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL") or _default_sqlite
    # Normalize DSN from whichever env source provided it.
    url = _normalize_database_url(url)
    if not url:
        return _default_sqlite
    return url


def _resolve_cors_origins() -> list[str]:
    """Resolve CORS origins from env. Kept outside pydantic-settings because
    the env var may be a comma-separated string, which pydantic-settings
    rejects when it expects a JSON list."""
    raw = os.environ.get("CORS_ORIGINS", "")
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return [s.strip() for s in raw.split(",") if s.strip()]


class Settings(BaseSettings):
    demo_mode: bool = False
    database_url: str = _resolve_database_url()
    booking_timezone: str = "America/Denver"
    session_expire_days: int = 14
    secret_key: str = _default_secret
    environment: str = "development"
    resend_api_key: str = ""
    resend_from_email: str = "Cabin Booking <noreply@no-reply.example.com>"
    app_url: str = "http://localhost:3000"
    invitation_expire_days: int = 14
    magic_link_expire_minutes: int = 45
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_checkout_timeout_minutes: int = 30

    class Config:
        env_file = (
            str(_project_root / ".env.local"),
            str(_project_root / ".env"),
        )  # .env overrides .env.local (rightmost wins)
        extra = "ignore"


settings = Settings()
# Prefer POSTGRES_URL when present, otherwise normalize the resolved setting value
# (which may come from DATABASE_URL via pydantic-settings env parsing).
if os.environ.get("POSTGRES_URL"):
    settings.database_url = _normalize_database_url(os.environ["POSTGRES_URL"])
else:
    settings.database_url = _normalize_database_url(settings.database_url)

# In development, always use local SQLite - env files may contain production DATABASE_URL
if settings.environment != "production":
    settings.database_url = _default_sqlite

# Public demos are isolated even if unrelated deployment variables are present.
if settings.demo_mode:
    settings.environment = "demo"
    settings.database_url = f"sqlite:///{Path(tempfile.mkdtemp(prefix='cabin-demo-')) / 'cabins.db'}"
    settings.resend_api_key = ""
    settings.stripe_secret_key = ""
    settings.stripe_publishable_key = ""
    settings.stripe_webhook_secret = ""

cors_origins = _resolve_cors_origins()

# In production, require an explicit SECRET_KEY
if settings.environment == "production" and settings.secret_key == _default_secret:
    raise RuntimeError(
        "SECRET_KEY must be set via environment variable in production. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

# In production, require an explicit STRIPE_WEBHOOK_SECRET so webhook signatures are verified
if settings.environment == "production" and settings.stripe_secret_key and not settings.stripe_webhook_secret:
    raise RuntimeError(
        "STRIPE_WEBHOOK_SECRET must be set via environment variable in production. "
        "Get it from Stripe Dashboard > Developers > Webhooks > Signing secret."
    )

from urllib.parse import urlsplit

from fastapi import Request

from config import settings


def _origin_from_header(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None

    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_local_origin(origin: str) -> bool:
    parsed = urlsplit(origin)
    return parsed.hostname in {"localhost", "127.0.0.1"}


def resolve_frontend_base_url(request: Request) -> str:
    """Use the active local frontend origin in development, otherwise fall back to APP_URL."""
    app_url = settings.app_url.rstrip("/")
    if settings.environment == "production":
        return app_url

    for header in ("origin", "referer"):
        origin = _origin_from_header(request.headers.get(header, ""))
        if origin and _is_local_origin(origin):
            return origin

    return app_url

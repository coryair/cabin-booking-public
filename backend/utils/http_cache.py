from fastapi import Response


def set_private_cache(response: Response, *, max_age: int = 30, stale_while_revalidate: int = 120) -> None:
    """Set conservative private cache headers for authenticated GET responses."""
    response.headers["Cache-Control"] = (
        f"private, max-age={max_age}, stale-while-revalidate={stale_while_revalidate}"
    )


def set_no_store(response: Response) -> None:
    """Disable intermediary and browser caching for sensitive responses."""
    response.headers["Cache-Control"] = "no-store"

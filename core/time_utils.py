from datetime import datetime, timezone


def now_utc() -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def time_since(dt: datetime) -> datetime:
    """Return a timedelta between now (UTC) and the provided datetime.

    dt is expected to be timezone-aware. Caller is responsible for ensuring
    dt is not None and is aware.
    """
    return now_utc() - dt

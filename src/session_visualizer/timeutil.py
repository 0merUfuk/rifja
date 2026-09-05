"""Event time is separate from import/observation time. Naive time stays unknown."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo


def now() -> str:
    return datetime.now(UTC).isoformat()


def normalize(value: str | None) -> tuple[str | None, str]:
    if value is None or value == "":
        return None, "missing"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError, AttributeError:
        return None, "invalid"
    if parsed.tzinfo is None:
        return None, "naive"
    return parsed.astimezone(UTC).isoformat(), "known"


def date_bounds(start: str, end: str | None, timezone: str) -> tuple[str, str]:
    zone = ZoneInfo(timezone)
    first = datetime.combine(datetime.fromisoformat(start).date(), time.min, zone)
    last = datetime.combine(
        datetime.fromisoformat(end or start).date() + timedelta(days=1), time.min, zone
    )
    if last <= first:
        raise ValueError("end_date_before_start")
    return first.astimezone(UTC).isoformat(), last.astimezone(UTC).isoformat()

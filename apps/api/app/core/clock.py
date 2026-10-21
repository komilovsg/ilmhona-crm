"""The one clock. «Now» and «today» (Asia/Dushanbe) come from here so a test can freeze them:
`clock.freeze(datetime(...))`, `clock.freeze(None)`. Production never freezes."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Dushanbe")
_frozen: datetime | None = None


def now() -> datetime:
    return _frozen or datetime.now(UTC)


def today() -> date:
    return now().astimezone(TZ).date()


def freeze(at: datetime | None) -> None:
    """Pin the clock to `at` (timezone-aware); None releases it."""
    global _frozen
    _frozen = at.astimezone(UTC) if at else None

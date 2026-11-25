from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


def parse_target_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must use YYYY-MM-DD format") from exc


def target_date_for_run(now: datetime, explicit: date | None = None) -> date:
    if explicit is not None:
        return explicit
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(SHANGHAI).date() - timedelta(days=1)


def shanghai_now() -> datetime:
    return datetime.now(tz=SHANGHAI)

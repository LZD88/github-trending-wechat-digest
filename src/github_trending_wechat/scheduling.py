from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
NIGHTLY_CAPTURE_TIME = time(23, 55)
NIGHTLY_CAPTURE_WINDOW = timedelta(hours=3)
MORNING_DELIVERY_TIME = time(8)


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


def capture_date(now: datetime, *, scheduled: bool = False) -> date:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(SHANGHAI)
    if not scheduled:
        return local.date()

    target = _capture_target(local)
    if target is None:
        raise ValueError("Scheduled capture is outside the 23:55–02:55 Beijing window")
    return target


def _capture_target(local: datetime) -> date | None:
    planned = datetime.combine(local.date(), NIGHTLY_CAPTURE_TIME, SHANGHAI)
    if local < planned:
        planned -= timedelta(days=1)
    return planned.date() if local - planned < NIGHTLY_CAPTURE_WINDOW else None


def scheduled_operation(now: datetime) -> tuple[str, date | None]:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(SHANGHAI)
    capture_target = _capture_target(local)
    if capture_target is not None:
        return "capture", capture_target
    if local.time() >= MORNING_DELIVERY_TIME:
        return "recover", local.date() - timedelta(days=1)
    return "idle", None

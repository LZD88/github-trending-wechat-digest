from datetime import UTC, date, datetime

import pytest

from github_trending_wechat.models import DigestSnapshot, TrendingEntry
from github_trending_wechat.scheduling import capture_date, parse_target_date, target_date_for_run


def test_scheduled_capture_keeps_previous_date_when_delayed_past_midnight() -> None:
    now = datetime.fromisoformat("2026-11-25T00:15:00+08:00")

    assert capture_date(now, scheduled=True) == date(2026, 11, 24)
    assert capture_date(now) == date(2026, 11, 25)


def test_scheduled_capture_rejects_later_data() -> None:
    now = datetime.fromisoformat("2026-11-25T00:55:00+08:00")

    with pytest.raises(ValueError, match="outside"):
        capture_date(now, scheduled=True)


def test_target_date_uses_shanghai_calendar_boundary() -> None:
    # 16:30 UTC is already the next day in Shanghai.
    now = datetime(2026, 11, 24, 16, 30, tzinfo=UTC)

    assert target_date_for_run(now) == date(2026, 11, 24)


def test_delayed_morning_run_still_targets_yesterday() -> None:
    now = datetime.fromisoformat("2026-11-25T10:45:00+08:00")

    assert target_date_for_run(now) == date(2026, 11, 24)


def test_explicit_date_overrides_clock_for_resend() -> None:
    now = datetime.fromisoformat("2026-11-25T08:00:00+08:00")

    assert target_date_for_run(now, date(2026, 11, 20)) == date(2026, 11, 20)


def test_invalid_date_has_actionable_error() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parse_target_date("24/11/2026")


def test_content_hash_changes_when_ranked_content_changes() -> None:
    base = DigestSnapshot(
        target_date=date(2026, 11, 24),
        fetched_at=datetime.now(UTC),
        source="github",
        basis="rolling",
        entries=[TrendingEntry(1, "a/one", "https://github.com/a/one")],
    )
    changed = DigestSnapshot.from_dict(base.to_dict())
    changed.entries[0].rank = 2

    assert base.compute_content_hash() != changed.compute_content_hash()

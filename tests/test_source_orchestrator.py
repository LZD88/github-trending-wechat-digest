from datetime import UTC, datetime

import pytest

from github_trending_wechat.models import TrendingEntry
from github_trending_wechat.sources import SourceError, SourceOrchestrator, SourceResult

NOW = datetime(2026, 11, 25, tzinfo=UTC)


class FakeSource:
    def __init__(self, result: SourceResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def fetch(self, now: datetime) -> SourceResult:
        self.calls += 1
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


def make_result(count: int, source: str = "primary") -> SourceResult:
    return SourceResult(
        entries=[
            TrendingEntry(
                rank=index + 1,
                full_name=f"owner/repo-{index}",
                url=f"https://github.com/owner/repo-{index}",
            )
            for index in range(count)
        ],
        source=source,
        fetched_at=NOW,
    )


def test_orchestrator_prefers_primary_and_keeps_first_ten() -> None:
    primary = FakeSource(make_result(12))
    fallback = FakeSource(make_result(10, "fallback"))

    result = SourceOrchestrator(primary, fallback).fetch_top(NOW)

    assert result.source == "primary"
    assert len(result.entries) == 10
    assert [entry.rank for entry in result.entries] == list(range(1, 11))
    assert fallback.calls == 0


def test_orchestrator_uses_fallback_when_primary_fails() -> None:
    primary = FakeSource(error=SourceError("primary unavailable"))
    fallback = FakeSource(make_result(10, "fallback"))

    result = SourceOrchestrator(primary, fallback).fetch_top(NOW)

    assert result.source == "fallback"
    assert primary.calls == 1
    assert fallback.calls == 1


def test_orchestrator_warns_when_fewer_than_ten_are_available() -> None:
    result = SourceOrchestrator(FakeSource(make_result(3)), FakeSource()).fetch_top(NOW)

    assert len(result.entries) == 3
    assert "本次仅获取到 3 个有效仓库" in result.warnings


def test_orchestrator_raises_when_all_sources_fail() -> None:
    orchestrator = SourceOrchestrator(
        FakeSource(error=SourceError("primary unavailable")),
        FakeSource(error=SourceError("fallback stale")),
    )

    with pytest.raises(SourceError, match="All trending sources failed"):
        orchestrator.fetch_top(NOW)

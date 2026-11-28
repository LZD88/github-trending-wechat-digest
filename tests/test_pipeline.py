from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from github_trending_wechat.delivery import DeliveryResult, DeliveryService
from github_trending_wechat.models import DigestSnapshot, TrendingEntry
from github_trending_wechat.pipeline import DigestApplication
from github_trending_wechat.sources import (
    GitHubRepositoryEnricher,
    HistoricalTrendingSource,
    SourceError,
    SourceResult,
)
from github_trending_wechat.storage import DeliveryStore, DigestStore
from github_trending_wechat.summarizer import ChineseSummarizer

NOW = datetime(2026, 11, 25, 0, 0, tzinfo=UTC)
CAPTURED = datetime(2026, 11, 24, 15, 55, tzinfo=UTC)


class OrderedSources:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def fetch_top(self, now: datetime) -> SourceResult:
        self.events.append("fetch")
        return SourceResult(
            entries=[
                TrendingEntry(
                    1,
                    "owner/repo",
                    "https://github.com/owner/repo",
                    original_description="English description",
                )
            ],
            source="primary",
            fetched_at=now,
            warnings=["source warning"],
        )


class OrderedSummarizer:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def apply(self, entries: list[TrendingEntry]) -> list[str]:
        self.events.append("summarize")
        entries[0].chinese_description = "中文简介"
        return ["summary warning"]


class OrderedProvider:
    name = "serverchan"
    recipient_fingerprint = "recipient"

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def send(self, title: str, segments: list[str]) -> DeliveryResult:
        self.events.append("deliver")
        assert "中文简介" in segments[0]
        return DeliveryResult(True, ["message"], 1)


def test_pipeline_orders_stages_and_persists_results(tmp_path: Path) -> None:
    events: list[str] = []
    application = DigestApplication(
        sources=OrderedSources(events),
        summarizer=OrderedSummarizer(events),
        digest_store=DigestStore(tmp_path),
        delivery_service=DeliveryService(
            OrderedProvider(events), DeliveryStore(tmp_path), now=lambda: NOW
        ),
        now=lambda: CAPTURED,
    )

    archived = application.capture(scheduled=True)
    assert events == ["fetch", "summarize"]
    application.now = lambda: datetime.fromisoformat("2026-11-25T00:17:00+08:00")
    assert application.capture(scheduled=True) == archived
    application.now = lambda: NOW
    outcome = application.run()
    application.now = lambda: datetime.fromisoformat("2026-11-25T08:17:00+08:00")
    backup = application.run()
    assert backup.attempt is not None and backup.attempt.status == "idempotent_skip"

    assert events == ["fetch", "summarize", "deliver"]
    assert outcome.snapshot == archived
    assert outcome.snapshot.fetched_at == CAPTURED
    assert outcome.attempt is not None and outcome.attempt.status == "success"
    assert outcome.snapshot.warnings == ["source warning", "summary warning"]
    assert DigestStore(tmp_path).load(date(2026, 11, 24)) is not None
    assert DeliveryStore(tmp_path).load(date(2026, 11, 24))[0].status == "success"


def test_capture_reuses_only_matching_valid_translations(tmp_path: Path) -> None:
    events: list[str] = []
    store = DigestStore(tmp_path)
    old = TrendingEntry(
        1, "owner/repo", "https://github.com/owner/repo", "English description", "有效译文"
    )
    placeholder = TrendingEntry(
        1, old.full_name, old.url, old.original_description, "该项目简介暂无法转换为中文。"
    )
    for day, entry in [(22, old), (23, placeholder)]:
        store.save(DigestSnapshot(date(2026, 11, day), CAPTURED, "primary", "daily", [entry]))

    def unavailable(request: httpx.Request) -> httpx.Response:
        events.append(request.url.host)
        return httpx.Response(200, json={"error": "response missing choices"})

    with httpx.Client(transport=httpx.MockTransport(unavailable)) as client:
        application = DigestApplication(
            sources=OrderedSources(events),
            summarizer=ChineseSummarizer(
                client, api_base="https://summary.test", api_key="example", public_fallback=True
            ),
            digest_store=store,
            delivery_service=None,
            now=lambda: CAPTURED,
        )
        snapshot = application.capture(scheduled=True)
        assert snapshot.entries[0].chinese_description == "有效译文"
        assert events == ["fetch"]

        old.original_description = "Older description"
        store.save(DigestSnapshot(date(2026, 11, 22), CAPTURED, "primary", "daily", [old]))
        snapshot = application.capture()
        assert snapshot.entries[0].chinese_description == "English description"
        assert snapshot.warnings[-1] == "1 个项目的中文简介暂不可用，已保留英文原文"
        assert events == ["fetch", "fetch", "summary.test", "api.mymemory.translated.net"]


def test_pipeline_preview_does_not_require_delivery(tmp_path: Path) -> None:
    events: list[str] = []
    application = DigestApplication(
        sources=OrderedSources(events),
        summarizer=OrderedSummarizer(events),
        digest_store=DigestStore(tmp_path),
        delivery_service=None,
        now=lambda: NOW,
    )

    outcome = application.preview()

    assert events == ["fetch", "summarize"]
    assert outcome.attempt is None
    assert DigestStore(tmp_path).load(date(2026, 11, 25)) is None


def test_resend_prefers_historical_snapshot_without_refetch(tmp_path: Path) -> None:
    events: list[str] = []
    digest_store = DigestStore(tmp_path)
    seed = DigestApplication(
        sources=OrderedSources(events),
        summarizer=OrderedSummarizer(events),
        digest_store=digest_store,
        delivery_service=None,
        now=lambda: datetime(2026, 11, 20, 15, 55, tzinfo=UTC),
    )
    seed.capture(scheduled=True)
    events.clear()
    application = DigestApplication(
        sources=OrderedSources(events),
        summarizer=OrderedSummarizer(events),
        digest_store=digest_store,
        delivery_service=DeliveryService(
            OrderedProvider(events), DeliveryStore(tmp_path), now=lambda: NOW
        ),
        now=lambda: NOW,
    )

    assert application.preview(date(2026, 11, 20)).snapshot.target_date == date(2026, 11, 20)
    outcome = application.resend(date(2026, 11, 20))

    assert events == ["deliver"]
    assert outcome.rendered.title.startswith("【补发】")
    assert outcome.attempt is not None and outcome.attempt.reason == "manual_resend"


def test_recovery_archives_and_sends_historical_rankings_once(tmp_path: Path) -> None:
    events: list[str] = []
    target = date(2026, 11, 24)
    published = "2026-11-24T12:50:10+00:00"
    sha = "a" * 40

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/commits"):
            assert request.url.params["path"].endswith("/(null).json")
            return httpx.Response(
                200, json=[{"sha": sha, "commit": {"committer": {"date": published}}}]
            )
        if request.url.host == "raw.githubusercontent.com":
            assert f"/{sha}/" in request.url.path
            return httpx.Response(
                200, json={"date": str(target), "language": None, "list": ["owner/repo"]}
            )
        return httpx.Response(200, json={"description": "English", "stargazers_count": 123})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        application = DigestApplication(
            sources=OrderedSources(events),
            summarizer=OrderedSummarizer(events),
            digest_store=DigestStore(tmp_path),
            delivery_service=DeliveryService(
                OrderedProvider(events), DeliveryStore(tmp_path), now=lambda: NOW
            ),
            now=lambda: NOW,
            historical_source=HistoricalTrendingSource(client, GitHubRepositoryEnricher(client)),
        )
        first = application.run(recover_missing=True)
        retry = application.run(recover_missing=True)
        with pytest.raises(SourceError, match="publication date does not match"):
            application.historical_source.fetch(date(2026, 11, 25))

    assert first.snapshot.fetched_at.isoformat() == published
    assert first.snapshot.entries[0].stars is None
    assert "归档时间" in first.rendered.segments[0]
    assert DigestStore(tmp_path).load(target) == first.snapshot
    assert first.attempt is not None and first.attempt.status == "success"
    assert retry.attempt is not None and retry.attempt.status == "idempotent_skip"
    assert len(DeliveryStore(tmp_path).load(target)) == 1
    assert events == ["summarize", "deliver"]


@pytest.mark.parametrize("operation", ["run", "resend", "preview"])
def test_missing_snapshot_does_not_fetch_or_send(tmp_path: Path, operation: str) -> None:
    events: list[str] = []
    application = DigestApplication(
        sources=OrderedSources(events),
        summarizer=OrderedSummarizer(events),
        digest_store=DigestStore(tmp_path),
        delivery_service=DeliveryService(
            OrderedProvider(events), DeliveryStore(tmp_path), now=lambda: NOW
        ),
        now=lambda: NOW,
    )

    with pytest.raises(SourceError, match="2026-11-20.*缺少"):
        getattr(application, operation)(date(2026, 11, 20))
    assert events == []
    assert DigestStore(tmp_path).load(date(2026, 11, 20)) is None

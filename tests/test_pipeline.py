from datetime import UTC, date, datetime
from pathlib import Path

from github_trending_wechat.delivery import DeliveryResult, DeliveryService
from github_trending_wechat.models import TrendingEntry
from github_trending_wechat.pipeline import DigestApplication
from github_trending_wechat.sources import SourceResult
from github_trending_wechat.storage import DeliveryStore, DigestStore

NOW = datetime(2026, 11, 25, 8, 0, tzinfo=UTC)


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
        now=lambda: NOW,
    )

    outcome = application.run(date(2026, 11, 24))

    assert events == ["fetch", "summarize", "deliver"]
    assert outcome.attempt is not None and outcome.attempt.status == "success"
    assert outcome.snapshot.warnings == ["source warning", "summary warning"]
    assert DigestStore(tmp_path).load(date(2026, 11, 24)) is not None
    assert DeliveryStore(tmp_path).load(date(2026, 11, 24))[0].status == "success"


def test_pipeline_preview_does_not_require_delivery(tmp_path: Path) -> None:
    events: list[str] = []
    application = DigestApplication(
        sources=OrderedSources(events),
        summarizer=OrderedSummarizer(events),
        digest_store=DigestStore(tmp_path),
        delivery_service=None,
        now=lambda: NOW,
    )

    outcome = application.preview(date(2026, 11, 24))

    assert events == ["fetch", "summarize"]
    assert outcome.attempt is None
    assert DigestStore(tmp_path).load(date(2026, 11, 24)) is None


def test_resend_prefers_historical_snapshot_without_refetch(tmp_path: Path) -> None:
    events: list[str] = []
    digest_store = DigestStore(tmp_path)
    seed = DigestApplication(
        sources=OrderedSources(events),
        summarizer=OrderedSummarizer(events),
        digest_store=digest_store,
        delivery_service=None,
        now=lambda: NOW,
    )
    seed.generate(date(2026, 11, 20), save=True)
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

    outcome = application.resend(date(2026, 11, 20))

    assert events == ["deliver"]
    assert outcome.rendered.title.startswith("【补发】")
    assert outcome.attempt is not None and outcome.attempt.reason == "manual_resend"


def test_resend_rebuilds_missing_snapshot_before_delivery(tmp_path: Path) -> None:
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

    outcome = application.resend(date(2026, 11, 20))

    assert events == ["fetch", "summarize", "deliver"]
    assert outcome.snapshot_changed is True
    assert DigestStore(tmp_path).load(date(2026, 11, 20)) is not None

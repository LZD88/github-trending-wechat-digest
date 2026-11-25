from datetime import UTC, date, datetime
from pathlib import Path

from github_trending_wechat.delivery import DeliveryResult, DeliveryService
from github_trending_wechat.models import DigestSnapshot, TrendingEntry
from github_trending_wechat.rendering import RenderedDigest
from github_trending_wechat.storage import DeliveryStore

NOW = datetime(2026, 11, 25, tzinfo=UTC)


class FakeProvider:
    name = "serverchan"
    recipient_fingerprint = "fingerprint"

    def __init__(self, results: list[DeliveryResult]) -> None:
        self.results = results
        self.calls = 0

    def send(self, title: str, segments: list[str]) -> DeliveryResult:
        result = self.results[self.calls]
        self.calls += 1
        return result


def snapshot() -> DigestSnapshot:
    value = DigestSnapshot(
        target_date=date(2026, 11, 24),
        fetched_at=NOW,
        source="github",
        basis="rolling",
        entries=[TrendingEntry(1, "owner/repo", "https://github.com/owner/repo")],
    )
    value.ensure_content_hash()
    return value


def rendered() -> RenderedDigest:
    return RenderedDigest("title", ["body"])


def test_successful_delivery_is_skipped_on_normal_rerun(tmp_path: Path) -> None:
    provider = FakeProvider([DeliveryResult(True, ["one"], 1)])
    service = DeliveryService(provider, DeliveryStore(tmp_path), now=lambda: NOW)

    first = service.deliver(snapshot(), rendered())
    second = service.deliver(snapshot(), rendered())

    assert first.status == "success"
    assert second.status == "idempotent_skip"
    assert second.related_attempt_key == first.idempotency_key
    assert provider.calls == 1


def test_failed_delivery_can_be_retried_by_next_run(tmp_path: Path) -> None:
    provider = FakeProvider(
        [
            DeliveryResult(False, [], 3, "temporary", "unavailable"),
            DeliveryResult(True, ["two"], 1),
        ]
    )
    service = DeliveryService(provider, DeliveryStore(tmp_path), now=lambda: NOW)

    first = service.deliver(snapshot(), rendered())
    second = service.deliver(snapshot(), rendered())

    assert first.status == "failed"
    assert second.status == "success"
    assert provider.calls == 2


def test_manual_resend_sends_again_and_links_original(tmp_path: Path) -> None:
    provider = FakeProvider([DeliveryResult(True, ["one"], 1), DeliveryResult(True, ["two"], 1)])
    store = DeliveryStore(tmp_path)
    service = DeliveryService(provider, store, now=lambda: NOW)

    first = service.deliver(snapshot(), rendered())
    resent = service.deliver(snapshot(), rendered(), force=True, reason="manual_resend")

    assert resent.status == "success"
    assert resent.reason == "manual_resend"
    assert resent.related_attempt_key == first.idempotency_key
    assert provider.calls == 2

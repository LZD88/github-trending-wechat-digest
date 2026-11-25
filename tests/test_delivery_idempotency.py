from datetime import UTC, date, datetime
from pathlib import Path

from github_trending_wechat.delivery import DeliveryResult, DeliveryService
from github_trending_wechat.models import DigestSnapshot, TrendingEntry, stable_json
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
    changed = snapshot()
    changed.entries[0].stars = 1000
    second = service.deliver(changed, rendered())

    assert first.status == "success"
    assert second.status == "idempotent_skip"
    assert second.related_attempt_key == first.idempotency_key
    assert provider.calls == 1


def test_legacy_success_still_blocks_a_rerun_and_archive_is_sanitized(tmp_path: Path) -> None:
    provider = FakeProvider([])
    store = DeliveryStore(tmp_path)
    service = DeliveryService(provider, store, now=lambda: NOW)
    digest = snapshot()
    path = store.path_for(digest.target_date)
    path.parent.mkdir()
    path.write_text(
        stable_json(
            [
                {
                    "provider": provider.name,
                    "recipient_fingerprint": provider.recipient_fingerprint,
                    "target_date": digest.target_date.isoformat(),
                    "attempted_at": NOW.isoformat(),
                    "status": "success",
                    "content_hash": "old-content-hash",
                    "idempotency_key": "old-version-key",
                    "message_ids": ["provider-read-key"],
                    "error_message": "raw HTTP diagnostics",
                },
            ]
        ),
        encoding="utf-8",
    )

    outcome = service.deliver(digest, rendered())

    assert outcome.status == "idempotent_skip"
    assert provider.calls == 0
    stored = path.read_text(encoding="utf-8")
    assert "message_ids" not in stored
    assert "error_message" not in stored
    assert "content_hash" not in stored


def test_same_issue_can_be_sent_to_a_different_recipient(tmp_path: Path) -> None:
    provider = FakeProvider([DeliveryResult(True, ["one"], 1), DeliveryResult(True, ["two"], 1)])
    service = DeliveryService(provider, DeliveryStore(tmp_path), now=lambda: NOW)

    assert service.deliver(snapshot(), rendered()).status == "success"
    provider.recipient_fingerprint = "other-recipient"
    assert service.deliver(snapshot(), rendered()).status == "success"
    assert provider.calls == 2


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

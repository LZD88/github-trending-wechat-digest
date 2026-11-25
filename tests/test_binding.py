from datetime import UTC, datetime
from pathlib import Path

from github_trending_wechat.delivery import DeliveryResult, DeliveryService
from github_trending_wechat.storage import DeliveryStore

NOW = datetime(2026, 11, 25, 8, 0, tzinfo=UTC)


class BindingProvider:
    name = "serverchan"
    recipient_fingerprint = "recipient"

    def __init__(self, result: DeliveryResult) -> None:
        self.result = result
        self.requests: list[tuple[str, list[str]]] = []

    def send(self, title: str, segments: list[str]) -> DeliveryResult:
        self.requests.append((title, segments))
        return self.result


def test_binding_success_records_message_id_and_context(tmp_path: Path) -> None:
    provider = BindingProvider(DeliveryResult(True, ["binding-message"], 1))
    store = DeliveryStore(tmp_path)
    service = DeliveryService(provider, store, now=lambda: NOW)

    attempt = service.test_binding("production")

    assert attempt.status == "binding_verified"
    assert attempt.message_ids == ["binding-message"]
    assert "production" in provider.requests[0][1][0]
    assert NOW.isoformat() in provider.requests[0][1][0]
    assert store.load(NOW.date())[0].status == "binding_verified"
    assert "binding-message" not in store.path_for(NOW.date()).read_text(encoding="utf-8")


def test_binding_failure_is_not_marked_verified(tmp_path: Path) -> None:
    provider = BindingProvider(DeliveryResult(False, [], 1, "authentication", "invalid key"))
    service = DeliveryService(provider, DeliveryStore(tmp_path), now=lambda: NOW)

    attempt = service.test_binding("production")

    assert attempt.status == "binding_failed"
    assert attempt.error_class == "authentication"
    assert attempt.message_ids == []

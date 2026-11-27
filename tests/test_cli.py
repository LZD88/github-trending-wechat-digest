from datetime import UTC, date, datetime

import pytest

from github_trending_wechat import cli
from github_trending_wechat.models import DeliveryAttempt, DigestSnapshot, TrendingEntry
from github_trending_wechat.pipeline import RunOutcome
from github_trending_wechat.rendering import RenderedDigest
from github_trending_wechat.sources import SourceError


def outcome(status: str = "success") -> RunOutcome:
    snapshot = DigestSnapshot(
        target_date=date(2026, 11, 24),
        fetched_at=datetime(2026, 11, 25, tzinfo=UTC),
        source="github",
        basis="rolling",
        entries=[TrendingEntry(1, "owner/repo", "https://github.com/owner/repo")],
    )
    snapshot.ensure_content_hash()
    attempt = DeliveryAttempt(
        provider="serverchan",
        recipient_fingerprint="recipient",
        target_date=snapshot.target_date,
        content_hash=snapshot.content_hash,
        status=status,
        attempted_at=snapshot.fetched_at,
        message_ids=["message"] if status == "success" else [],
    )
    return RunOutcome(snapshot, RenderedDigest("title", ["PREVIEW BODY"]), attempt)


class FakeApplication:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.error: Exception | None = None
        self.run_status = "success"

    def preview(self, target: date | None, *, save: bool) -> RunOutcome:
        self.calls.append(("preview", target, save))
        if self.error:
            raise self.error
        result = outcome()
        result.attempt = None
        return result

    def run(self, target: date | None, *, recover_missing: bool = False) -> RunOutcome:
        self.calls.append(("run", target, recover_missing))
        if self.error:
            raise self.error
        return outcome(self.run_status)

    def resend(self, target: date) -> RunOutcome:
        self.calls.append(("resend", target))
        return outcome()

    def test_binding(self, environment: str) -> DeliveryAttempt:
        self.calls.append(("test-binding", environment))
        result = outcome().attempt
        assert result is not None
        result.status = "binding_verified"
        return result


@pytest.fixture
def fake_application(monkeypatch: pytest.MonkeyPatch) -> FakeApplication:
    application = FakeApplication()
    monkeypatch.setenv("SERVERCHAN_SENDKEY", "SCT_TEST")
    monkeypatch.setattr(cli, "build_application", lambda *args, **kwargs: application)
    return application


def test_preview_outputs_content_and_never_calls_delivery(
    fake_application: FakeApplication, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["preview", "--date", "2026-11-24", "--save"])

    assert code == 0
    assert fake_application.calls == [("preview", date(2026, 11, 24), True)]
    assert "PREVIEW BODY" in capsys.readouterr().out


def test_run_reports_success(
    fake_application: FakeApplication, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["run", "--date", "2026-11-24"])

    assert code == 0
    assert fake_application.calls == [("run", date(2026, 11, 24), False)]
    assert "delivery=success" in capsys.readouterr().out


def test_run_treats_idempotent_skip_as_success(
    fake_application: FakeApplication, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_application.run_status = "idempotent_skip"

    code = cli.main(["run"])

    assert code == 0
    assert "delivery=idempotent_skip" in capsys.readouterr().out


def test_stale_source_failure_returns_nonzero_without_secret(
    fake_application: FakeApplication,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_application.error = SourceError("stale data; sendkey=SCT_SECRET")
    monkeypatch.setenv("SERVERCHAN_SENDKEY", "SCT_SECRET")

    code = cli.main(["run"])

    captured = capsys.readouterr()
    assert code == 1
    assert "SCT_SECRET" not in captured.err


def test_resend_and_binding_commands_are_dispatched(fake_application: FakeApplication) -> None:
    assert cli.main(["resend", "--date", "2026-11-20"]) == 0
    assert cli.main(["test-binding", "--environment", "prod"]) == 0

    assert fake_application.calls == [
        ("resend", date(2026, 11, 20)),
        ("test-binding", "prod"),
    ]

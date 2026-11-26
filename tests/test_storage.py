import json
from datetime import UTC, date, datetime
from pathlib import Path

from github_trending_wechat.models import DeliveryAttempt, DigestSnapshot, TrendingEntry
from github_trending_wechat.storage import DeliveryStore, DigestStore


def snapshot(description: str = "示例") -> DigestSnapshot:
    return DigestSnapshot(
        target_date=date(2026, 11, 24),
        fetched_at=datetime(2026, 11, 25, tzinfo=UTC),
        source="github",
        basis="rolling daily",
        entries=[
            TrendingEntry(
                1,
                "owner/repo",
                "https://github.com/owner/repo",
                original_description=description,
                chinese_description=description,
            )
        ],
    )


def test_digest_store_round_trip_uses_date_path(tmp_path: Path) -> None:
    store = DigestStore(tmp_path)

    saved, changed = store.save(snapshot())
    loaded = store.load(date(2026, 11, 24))

    assert changed is True
    assert loaded == saved
    assert store.path_for(saved.target_date) == tmp_path / "digests" / "2026-11-24.json"


def test_digest_store_reuses_identical_snapshot(tmp_path: Path) -> None:
    store = DigestStore(tmp_path)
    first, _ = store.save(snapshot())
    later = snapshot()
    later.fetched_at = datetime(2026, 11, 25, 1, tzinfo=UTC)

    reused, changed = store.save(later)

    assert changed is False
    assert reused.fetched_at == first.fetched_at


def test_digest_store_replaces_changed_content(tmp_path: Path) -> None:
    store = DigestStore(tmp_path)
    first, _ = store.save(snapshot("第一版"))

    second, changed = store.save(snapshot("第二版"))

    assert changed is True
    assert second.content_hash != first.content_hash


def test_digest_snapshot_file_contains_no_secret_fields(tmp_path: Path) -> None:
    store = DigestStore(tmp_path)
    item, _ = store.save(snapshot())

    text = store.path_for(item.target_date).read_text(encoding="utf-8").lower()

    assert "sendkey" not in text
    assert "api_key" not in text
    assert "authorization" not in text


def test_delivery_store_accepts_legacy_single_record_and_appends(tmp_path: Path) -> None:
    store = DeliveryStore(tmp_path)
    target_date = date(2026, 11, 25)
    attempted_at = datetime(2026, 11, 25, tzinfo=UTC)
    legacy = DeliveryAttempt(
        "serverchan", "recipient", target_date, "", "binding_verified", attempted_at
    )
    path = store.path_for(target_date)
    path.parent.mkdir()
    path.write_text(json.dumps(legacy.to_dict()), encoding="utf-8")

    assert store.successful(target_date, "serverchan", "recipient") is None
    delivered = DeliveryAttempt("serverchan", "recipient", target_date, "", "success", attempted_at)
    store.append(delivered)

    assert store.load(target_date) == [legacy, delivered]
    assert store.successful(target_date, "serverchan", "recipient") == delivered

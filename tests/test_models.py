import json
from datetime import UTC, date, datetime

from github_trending_wechat.models import (
    DeliveryAttempt,
    DigestSnapshot,
    TrendingEntry,
    stable_json,
)


def sample_snapshot() -> DigestSnapshot:
    return DigestSnapshot(
        target_date=date(2026, 11, 24),
        fetched_at=datetime(2026, 11, 25, 0, 5, tzinfo=UTC),
        source="github",
        basis="GitHub daily rolling window",
        entries=[
            TrendingEntry(
                rank=1,
                full_name="owner/repo",
                url="https://github.com/owner/repo",
                original_description="Example",
                chinese_description="示例",
                language="Python",
                stars=10,
                stars_today=2,
            )
        ],
    )


def test_snapshot_round_trip_preserves_entries_and_order() -> None:
    snapshot = sample_snapshot()
    encoded = stable_json(snapshot.to_dict())
    decoded = DigestSnapshot.from_dict(json.loads(encoded))

    assert decoded == snapshot
    assert decoded.entries[0].rank == 1
    assert decoded.content_hash == snapshot.compute_content_hash()


def test_snapshot_hash_is_independent_of_fetch_time() -> None:
    first = sample_snapshot()
    second = sample_snapshot()
    second.fetched_at = datetime(2026, 11, 25, 1, 5, tzinfo=UTC)

    assert first.compute_content_hash() == second.compute_content_hash()


def test_delivery_attempt_round_trip_and_idempotency_key() -> None:
    attempt = DeliveryAttempt(
        provider="serverchan",
        recipient_fingerprint="abc123",
        target_date=date(2026, 11, 24),
        content_hash="digest-hash",
        status="success",
        attempted_at=datetime(2026, 11, 25, tzinfo=UTC),
        attempt_count=1,
        message_ids=["message-1"],
    )

    decoded = DeliveryAttempt.from_dict(json.loads(stable_json(attempt.to_dict())))

    assert decoded.message_ids == []
    assert decoded.content_hash == ""
    assert decoded.status == attempt.status
    assert decoded.idempotency_key == attempt.idempotency_key


def test_stable_json_is_key_sorted_and_unicode_readable() -> None:
    value = stable_json({"z": 1, "a": "中文"})

    assert value.index('"a"') < value.index('"z"')
    assert "中文" in value

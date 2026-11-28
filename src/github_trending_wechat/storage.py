from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

from github_trending_wechat.models import DeliveryAttempt, DigestSnapshot, stable_json

LOGGER = logging.getLogger(__name__)


class DigestStore:
    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / "digests"

    def path_for(self, target_date: date) -> Path:
        return self.directory / f"{target_date.isoformat()}.json"

    def load(self, target_date: date) -> DigestSnapshot | None:
        path = self.path_for(target_date)
        if not path.exists():
            return None
        return DigestSnapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def recent_snapshots(self, before: date) -> Iterator[DigestSnapshot]:
        lookback = min(7, before.toordinal() - 1)
        for offset in range(1, lookback + 1):
            target = before - timedelta(days=offset)
            try:
                snapshot = self.load(target)
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                LOGGER.warning("Unable to read previous digest for %s", target)
                continue
            if snapshot is not None and snapshot.target_date == target:
                yield snapshot

    def save(self, snapshot: DigestSnapshot) -> tuple[DigestSnapshot, bool]:
        snapshot.ensure_content_hash()
        existing = self.load(snapshot.target_date)
        if existing and existing.content_hash == snapshot.content_hash:
            return existing, False
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path_for(snapshot.target_date).write_text(
            stable_json(snapshot.to_dict()), encoding="utf-8"
        )
        return snapshot, True


class DeliveryStore:
    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / "deliveries"

    def path_for(self, target_date: date) -> Path:
        return self.directory / f"{target_date.isoformat()}.json"

    def load(self, target_date: date) -> list[DeliveryAttempt]:
        path = self.path_for(target_date)
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = [data]
        return [DeliveryAttempt.from_dict(item) for item in data]

    def append(self, attempt: DeliveryAttempt) -> None:
        attempts = self.load(attempt.target_date)
        attempts.append(attempt)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path_for(attempt.target_date).write_text(
            stable_json([item.to_dict() for item in attempts]), encoding="utf-8"
        )

    def successful(
        self, target_date: date, provider: str, recipient_fingerprint: str
    ) -> DeliveryAttempt | None:
        return next(
            (
                item
                for item in self.load(target_date)
                if item.provider == provider
                and item.recipient_fingerprint == recipient_fingerprint
                and item.status == "success"
            ),
            None,
        )

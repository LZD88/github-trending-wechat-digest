from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from hashlib import sha256
from typing import Any, Self


@dataclass(slots=True)
class TrendingEntry:
    rank: int
    full_name: str
    url: str
    original_description: str = ""
    chinese_description: str = ""
    language: str | None = None
    stars: int | None = None
    stars_today: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(**data)


@dataclass(slots=True)
class DigestSnapshot:
    target_date: date
    fetched_at: datetime
    source: str
    basis: str
    entries: list[TrendingEntry]
    content_hash: str = ""
    warnings: list[str] = field(default_factory=list)

    def canonical_content(self) -> dict[str, Any]:
        return {
            "target_date": self.target_date.isoformat(),
            "source": self.source,
            "basis": self.basis,
            "entries": [asdict(entry) for entry in self.entries],
            "warnings": list(self.warnings),
        }

    def compute_content_hash(self) -> str:
        payload = json.dumps(
            self.canonical_content(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(payload).hexdigest()

    def ensure_content_hash(self) -> str:
        computed = self.compute_content_hash()
        self.content_hash = computed
        return computed

    def to_dict(self) -> dict[str, Any]:
        if not self.content_hash:
            self.ensure_content_hash()
        return {
            "target_date": self.target_date.isoformat(),
            "fetched_at": self.fetched_at.isoformat(),
            "source": self.source,
            "basis": self.basis,
            "entries": [asdict(entry) for entry in self.entries],
            "content_hash": self.content_hash,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            target_date=date.fromisoformat(data["target_date"]),
            fetched_at=datetime.fromisoformat(data["fetched_at"]),
            source=data["source"],
            basis=data["basis"],
            entries=[TrendingEntry.from_dict(item) for item in data["entries"]],
            content_hash=data.get("content_hash", ""),
            warnings=list(data.get("warnings", [])),
        )


@dataclass(slots=True)
class DeliveryAttempt:
    provider: str
    recipient_fingerprint: str
    target_date: date
    content_hash: str
    status: str
    attempted_at: datetime
    attempt_count: int = 0
    message_ids: list[str] = field(default_factory=list)
    error_class: str | None = None
    error_message: str | None = None
    reason: str = "scheduled"
    related_attempt_key: str | None = None

    @property
    def idempotency_key(self) -> str:
        raw = "|".join(
            [
                self.provider,
                self.recipient_fingerprint,
                self.target_date.isoformat(),
                self.content_hash,
            ]
        )
        return sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["target_date"] = self.target_date.isoformat()
        data["attempted_at"] = self.attempted_at.isoformat()
        data["idempotency_key"] = self.idempotency_key
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        values = dict(data)
        values.pop("idempotency_key", None)
        values["target_date"] = date.fromisoformat(values["target_date"])
        values["attempted_at"] = datetime.fromisoformat(values["attempted_at"])
        return cls(**values)


def stable_json(data: dict[str, Any] | list[Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Protocol

import httpx

from github_trending_wechat.models import DeliveryAttempt, DigestSnapshot
from github_trending_wechat.rendering import RenderedDigest
from github_trending_wechat.storage import DeliveryStore


class DeliveryError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, category: str) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.category = category


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    success: bool
    message_ids: list[str] = field(default_factory=list)
    attempt_count: int = 0
    error_category: str | None = None
    error_message: str | None = None


class DeliveryProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def recipient_fingerprint(self) -> str: ...

    def send(self, title: str, segments: Sequence[str]) -> DeliveryResult: ...


class ServerChanProvider:
    name = "serverchan"

    def __init__(
        self,
        client: httpx.Client,
        sendkey: str,
        *,
        api_base: str = "https://sctapi.ftqq.com",
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
        max_title_chars: int = 64,
        max_body_chars: int = 32_000,
    ) -> None:
        if not sendkey:
            raise ValueError("ServerChan SendKey is required")
        self.client = client
        self._sendkey = sendkey
        self.api_base = api_base.rstrip("/")
        self.max_attempts = max_attempts
        self.sleep = sleep
        self.jitter = jitter
        self.max_title_chars = max_title_chars
        self.max_body_chars = max_body_chars

    @property
    def recipient_fingerprint(self) -> str:
        digest = sha256(f"serverchan:{self._sendkey}".encode()).hexdigest()
        return digest[:16]

    def send(self, title: str, segments: Sequence[str]) -> DeliveryResult:
        if not title or len(title) > self.max_title_chars:
            raise DeliveryError(
                f"title must contain 1-{self.max_title_chars} characters",
                retryable=False,
                category="validation",
            )
        if not segments:
            raise DeliveryError(
                "at least one message segment is required", retryable=False, category="validation"
            )
        if any(not segment or len(segment) > self.max_body_chars for segment in segments):
            raise DeliveryError(
                f"each message body must contain 1-{self.max_body_chars} characters",
                retryable=False,
                category="validation",
            )

        message_ids: list[str] = []
        total_attempts = 0
        try:
            for index, segment in enumerate(segments, start=1):
                segment_title = (
                    title if len(segments) == 1 else f"{title} ({index}/{len(segments)})"
                )
                message_id, attempts = self._send_with_retry(segment_title, segment)
                total_attempts += attempts
                message_ids.append(message_id)
        except DeliveryError as exc:
            return DeliveryResult(
                success=False,
                message_ids=message_ids,
                attempt_count=total_attempts + getattr(exc, "attempt_count", 1),
                error_category=exc.category,
                error_message=str(exc),
            )
        return DeliveryResult(success=True, message_ids=message_ids, attempt_count=total_attempts)

    def _send_with_retry(self, title: str, body: str) -> tuple[str, int]:
        last_error: DeliveryError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._send_once(title, body), attempt
            except DeliveryError as exc:
                last_error = exc
                exc.attempt_count = attempt
                if not exc.retryable or attempt == self.max_attempts:
                    raise
                self.sleep((2 ** (attempt - 1)) + self.jitter())
        assert last_error is not None
        raise last_error

    def _send_once(self, title: str, body: str) -> str:
        try:
            response = self.client.post(
                f"{self.api_base}/{self._sendkey}.send",
                data={"title": title, "desp": body},
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise DeliveryError(
                "ServerChan connection failed or timed out", retryable=True, category="network"
            ) from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise DeliveryError(
                f"ServerChan temporary HTTP {response.status_code}",
                retryable=True,
                category="temporary",
            )
        if response.status_code in {401, 403}:
            raise DeliveryError(
                "ServerChan authentication failed",
                retryable=False,
                category="authentication",
            )
        if 400 <= response.status_code < 500:
            raise DeliveryError(
                f"ServerChan rejected request with HTTP {response.status_code}",
                retryable=False,
                category="request",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise DeliveryError(
                "ServerChan returned invalid JSON", retryable=True, category="temporary"
            ) from exc
        code = payload.get("code") if isinstance(payload, dict) else None
        if type(code) is not int:
            raise DeliveryError(
                "ServerChan response did not include a valid status code",
                retryable=True,
                category="temporary",
            )
        if code != 0:
            category = "authentication" if code in {40001, 40002} else "request"
            raise DeliveryError(
                f"ServerChan API error code {code}", retryable=False, category=category
            )
        data = payload.get("data")
        message_id = data.get("pushid") if isinstance(data, dict) else None
        return str(message_id or "accepted")


class DeliveryService:
    def __init__(
        self,
        provider: DeliveryProvider,
        store: DeliveryStore,
        *,
        now: Callable[[], datetime],
    ) -> None:
        self.provider = provider
        self.store = store
        self.now = now

    def deliver(
        self,
        snapshot: DigestSnapshot,
        rendered: RenderedDigest,
        *,
        force: bool = False,
        reason: str = "scheduled",
        record_skip: bool = True,
    ) -> DeliveryAttempt:
        probe = DeliveryAttempt(
            provider=self.provider.name,
            recipient_fingerprint=self.provider.recipient_fingerprint,
            target_date=snapshot.target_date,
            content_hash=snapshot.content_hash or snapshot.ensure_content_hash(),
            status="pending",
            attempted_at=self.now(),
            reason=reason,
        )
        prior = self.store.successful(
            snapshot.target_date, probe.provider, probe.recipient_fingerprint
        )
        if prior and not force:
            skipped = DeliveryAttempt(
                provider=probe.provider,
                recipient_fingerprint=probe.recipient_fingerprint,
                target_date=probe.target_date,
                content_hash=probe.content_hash,
                status="idempotent_skip",
                attempted_at=self.now(),
                reason=reason,
                related_attempt_key=prior.idempotency_key,
            )
            if record_skip:
                self.store.append(skipped)
            return skipped

        result = self.provider.send(rendered.title, rendered.segments)
        attempt = DeliveryAttempt(
            provider=probe.provider,
            recipient_fingerprint=probe.recipient_fingerprint,
            target_date=probe.target_date,
            content_hash=probe.content_hash,
            status="success" if result.success else "failed",
            attempted_at=self.now(),
            attempt_count=result.attempt_count,
            message_ids=result.message_ids,
            error_class=result.error_category,
            error_message=result.error_message,
            reason=reason,
            related_attempt_key=prior.idempotency_key if prior else None,
        )
        self.store.append(attempt)
        return attempt

    def test_binding(self, environment: str) -> DeliveryAttempt:
        attempted_at = self.now()
        title = "GitHub 热榜助手 · 绑定测试"
        body = "\n".join(
            [
                "# 绑定测试成功到达",
                "",
                f"- 环境：`{environment}`",
                f"- 测试时间：{attempted_at.isoformat()}",
                "",
                "这不是正式榜单。收到本消息说明 Server酱已连接到当前微信。",
            ]
        )
        content_hash = sha256(body.encode("utf-8")).hexdigest()
        result = self.provider.send(title, [body])
        attempt = DeliveryAttempt(
            provider=self.provider.name,
            recipient_fingerprint=self.provider.recipient_fingerprint,
            target_date=attempted_at.date(),
            content_hash=content_hash,
            status="binding_verified" if result.success else "binding_failed",
            attempted_at=attempted_at,
            attempt_count=result.attempt_count,
            message_ids=result.message_ids,
            error_class=result.error_category,
            error_message=result.error_message,
            reason="binding_test",
        )
        self.store.append(attempt)
        return attempt

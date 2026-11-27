from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx

from github_trending_wechat.config import Settings
from github_trending_wechat.delivery import DeliveryService, ServerChanProvider
from github_trending_wechat.models import DeliveryAttempt, DigestSnapshot
from github_trending_wechat.rendering import RenderedDigest, render_digest
from github_trending_wechat.scheduling import capture_date, shanghai_now, target_date_for_run
from github_trending_wechat.sources import (
    GitHubRepositoryEnricher,
    GitHubTrendingSource,
    HistoricalTrendingSource,
    JsonFallbackSource,
    SourceError,
    SourceOrchestrator,
    SourceResult,
)
from github_trending_wechat.storage import DeliveryStore, DigestStore
from github_trending_wechat.summarizer import ChineseSummarizer


@dataclass(slots=True)
class RunOutcome:
    snapshot: DigestSnapshot
    rendered: RenderedDigest
    attempt: DeliveryAttempt | None = None
    snapshot_changed: bool = False


class DigestApplication:
    def __init__(
        self,
        *,
        sources: SourceOrchestrator,
        summarizer: ChineseSummarizer,
        digest_store: DigestStore,
        delivery_service: DeliveryService | None,
        now: Callable[[], datetime] = shanghai_now,
        historical_source: HistoricalTrendingSource | None = None,
    ) -> None:
        self.sources = sources
        self.summarizer = summarizer
        self.digest_store = digest_store
        self.delivery_service = delivery_service
        self.now = now
        self.historical_source = historical_source

    def _build_snapshot(self, target_date: date, source_result: SourceResult) -> DigestSnapshot:
        warnings = list(source_result.warnings or [])
        warnings.extend(self.summarizer.apply(source_result.entries))
        snapshot = DigestSnapshot(
            target_date=target_date,
            fetched_at=source_result.fetched_at,
            source=source_result.source,
            basis=source_result.basis,
            entries=source_result.entries,
            warnings=warnings,
        )
        snapshot.ensure_content_hash()
        return snapshot

    def _capture(
        self, current: datetime, target_date: date, *, save: bool
    ) -> tuple[DigestSnapshot, bool]:
        snapshot = self._build_snapshot(target_date, self.sources.fetch_top(current))
        if save:
            return self.digest_store.save(snapshot)
        return snapshot, False

    def capture(self, *, scheduled: bool = False) -> DigestSnapshot:
        now = self.now()
        target_date = capture_date(now, scheduled=scheduled)
        if scheduled:
            archived = self.digest_store.load(target_date)
            if archived is not None:
                return archived
        snapshot, _ = self._capture(now, target_date, save=True)
        return snapshot

    def archived_snapshot(self, target_date: date) -> DigestSnapshot:
        snapshot = self.digest_store.load(target_date)
        if snapshot is None:
            raise SourceError(f"榜期 {target_date} 缺少已归档的热榜快照")
        return snapshot

    def preview(self, explicit_date: date | None = None, *, save: bool = False) -> RunOutcome:
        if explicit_date is not None:
            if save:
                raise ValueError("--save cannot be used with an archived date")
            snapshot = self.archived_snapshot(explicit_date)
            return RunOutcome(snapshot, render_digest(snapshot))
        now = self.now()
        snapshot, changed = self._capture(now, capture_date(now), save=save)
        return RunOutcome(snapshot, render_digest(snapshot), snapshot_changed=changed)

    def run(
        self, explicit_date: date | None = None, *, recover_missing: bool = False
    ) -> RunOutcome:
        service = self._require_delivery_service()
        target_date = target_date_for_run(self.now(), explicit_date)
        snapshot = self.digest_store.load(target_date)
        if snapshot is None:
            if not recover_missing or self.historical_source is None:
                raise SourceError(f"榜期 {target_date} 缺少已归档的热榜快照")
            snapshot = self._build_snapshot(target_date, self.historical_source.fetch(target_date))
            snapshot, _ = self.digest_store.save(snapshot)
        rendered = render_digest(snapshot)
        attempt = service.deliver(snapshot, rendered, record_skip=not recover_missing)
        return RunOutcome(snapshot, rendered, attempt)

    def resend(self, target_date: date) -> RunOutcome:
        service = self._require_delivery_service()
        snapshot = self.archived_snapshot(target_date)
        rendered = render_digest(snapshot, resend=True)
        attempt = service.deliver(snapshot, rendered, force=True, reason="manual_resend")
        return RunOutcome(snapshot, rendered, attempt)

    def test_binding(self, environment: str) -> DeliveryAttempt:
        return self._require_delivery_service().test_binding(environment)

    def _require_delivery_service(self) -> DeliveryService:
        if self.delivery_service is None:
            raise RuntimeError("delivery service is not configured")
        return self.delivery_service


def build_application(
    settings: Settings,
    *,
    require_delivery: bool,
    now: Callable[[], datetime] = shanghai_now,
) -> DigestApplication:
    client = httpx.Client(timeout=settings.http_timeout_seconds, follow_redirects=True)
    enricher = GitHubRepositoryEnricher(client, settings.github_token)
    sources = SourceOrchestrator(
        GitHubTrendingSource(client),
        JsonFallbackSource(client, timedelta(hours=settings.fallback_max_age_hours)),
        enricher,
    )
    summarizer = ChineseSummarizer(
        client,
        api_base=settings.summary_api_base,
        api_key=settings.summary_api_key,
        model=settings.summary_model,
        public_fallback=settings.summary_public_fallback,
    )
    digest_store = DigestStore(settings.data_dir)
    delivery_service = None
    if require_delivery:
        if not settings.serverchan_sendkey:
            raise RuntimeError("SERVERCHAN_SENDKEY is required for delivery")
        provider = ServerChanProvider(
            client,
            settings.serverchan_sendkey,
            api_base=settings.serverchan_api_base,
        )
        delivery_service = DeliveryService(provider, DeliveryStore(settings.data_dir), now=now)
    return DigestApplication(
        sources=sources,
        summarizer=summarizer,
        digest_store=digest_store,
        delivery_service=delivery_service,
        now=now,
        historical_source=HistoricalTrendingSource(client, enricher),
    )

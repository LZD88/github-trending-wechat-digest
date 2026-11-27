from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Protocol

import httpx

from github_trending_wechat.models import TrendingEntry
from github_trending_wechat.scheduling import SHANGHAI

LOGGER = logging.getLogger(__name__)
GITHUB_TRENDING_URL = "https://github.com/trending?since=daily"
FALLBACK_TRENDING_URL = (
    "https://raw.githubusercontent.com/isboyjc/github-trending-api/main/data/daily/all.json"
)
HISTORICAL_ARCHIVE_REPO = "antonkomarev/github-trending-archive"
ROLLING_BASIS = "GitHub daily Trending 滚动榜；抓取时刻快照，不代表北京时间自然日精确增量"


class SourceError(RuntimeError):
    """Raised when a trending source cannot produce a fresh valid result."""


@dataclass(slots=True)
class SourceResult:
    entries: list[TrendingEntry]
    source: str
    fetched_at: datetime
    basis: str = ROLLING_BASIS
    warnings: list[str] | None = None


class TrendingSource(Protocol):
    def fetch(self, now: datetime) -> SourceResult: ...


def parse_count(value: str | int | None) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"[^0-9]", "", str(value))
    return int(digits) if digits else None


class _TrendingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[dict[str, Any]] = []
        self._article_depth = 0
        self._current: dict[str, Any] | None = None
        self._in_repository_heading = False
        self._capture: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = set((attr.get("class") or "").split())
        if tag == "article" and "Box-row" in classes and self._current is None:
            self._article_depth = 1
            self._current = {}
            self._in_repository_heading = False
            return
        if self._current is None:
            return
        if tag == "article":
            self._article_depth += 1
        if tag == "h2":
            self._in_repository_heading = True
        href = attr.get("href") or ""
        if (
            tag == "a"
            and self._in_repository_heading
            and _valid_repo_href(href)
            and "full_name" not in self._current
        ):
            self._current["full_name"] = href.strip("/")
        if tag == "p" and "col-9" in classes:
            self._start_capture("description")
        elif attr.get("itemprop") == "programmingLanguage":
            self._start_capture("language")
        elif tag == "span" and "float-sm-right" in classes:
            self._start_capture("stars_today")
        elif tag == "a" and href.endswith("/stargazers"):
            self._start_capture("stars")

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "h2":
            self._in_repository_heading = False
        if self._capture and tag in {"p", "span", "a"}:
            value = " ".join("".join(self._text).split())
            if self._capture == "stars_today":
                match = re.search(r"([\d,]+)\s+stars?\s+today", value, re.I)
                self._current[self._capture] = parse_count(match.group(1)) if match else None
            elif self._capture == "stars":
                self._current[self._capture] = parse_count(value)
            else:
                self._current[self._capture] = value
            self._capture = None
            self._text.clear()
        if tag == "article":
            self._article_depth -= 1
            if self._article_depth == 0:
                self.entries.append(self._current)
                self._current = None

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._text.append(data)

    def _start_capture(self, name: str) -> None:
        self._capture = name
        self._text.clear()


def _valid_repo_href(href: str) -> bool:
    parts = href.strip("/").split("/")
    return (
        href.startswith("/")
        and len(parts) == 2
        and all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts)
    )


def parse_trending_html(html: str) -> list[TrendingEntry]:
    parser = _TrendingParser()
    parser.feed(html)
    entries: list[TrendingEntry] = []
    for item in parser.entries:
        full_name = item.get("full_name")
        if not full_name:
            LOGGER.warning("Skipping trending article without a valid repository identity")
            continue
        entries.append(
            TrendingEntry(
                rank=len(entries) + 1,
                full_name=full_name,
                url=f"https://github.com/{full_name}",
                original_description=item.get("description", ""),
                chinese_description="",
                language=item.get("language") or None,
                stars=item.get("stars"),
                stars_today=item.get("stars_today"),
            )
        )
    return entries


class GitHubTrendingSource:
    def __init__(self, client: httpx.Client, url: str = GITHUB_TRENDING_URL) -> None:
        self.client = client
        self.url = url

    def fetch(self, now: datetime) -> SourceResult:
        response = self.client.get(
            self.url,
            headers={"User-Agent": "github-trending-wechat/0.1"},
        )
        response.raise_for_status()
        entries = parse_trending_html(response.text)
        if not entries:
            raise SourceError("GitHub Trending returned no valid repositories")
        return SourceResult(entries=entries, source="github-trending", fetched_at=now)


class GitHubRepositoryEnricher:
    def __init__(
        self,
        client: httpx.Client,
        token: str | None = None,
        api_base: str = "https://api.github.com",
    ) -> None:
        self.client = client
        self.token = token
        self.api_base = api_base.rstrip("/")

    def enrich(
        self, entries: list[TrendingEntry], *, include_stars: bool = True
    ) -> list[TrendingEntry]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        for entry in entries:
            try:
                response = self.client.get(
                    f"{self.api_base}/repos/{entry.full_name}", headers=headers
                )
                response.raise_for_status()
                data = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                LOGGER.warning("Metadata enrichment failed for %s: %s", entry.full_name, exc)
                continue
            entry.original_description = data.get("description") or entry.original_description
            entry.language = data.get("language") or entry.language
            if include_stars:
                entry.stars = data.get("stargazers_count", entry.stars)
        return entries


class HistoricalTrendingSource:
    def __init__(self, client: httpx.Client, enricher: GitHubRepositoryEnricher) -> None:
        self.client = client
        self.enricher = enricher

    def fetch(self, target: date) -> SourceResult:
        path = f"archive/repository/{target.year}/{target.isoformat()}/(null).json"
        headers = {"Authorization": f"Bearer {self.enricher.token}"} if self.enricher.token else {}
        try:
            response = self.client.get(
                f"https://api.github.com/repos/{HISTORICAL_ARCHIVE_REPO}/commits",
                params={"path": path, "per_page": 1},
                headers=headers,
            )
            response.raise_for_status()
            commits = response.json()
            if not commits:
                raise SourceError(f"榜期 {target} 暂无可用的历史归档")
            revision = commits[0]
            sha = revision["sha"]
            if not re.fullmatch(r"[a-f0-9]{40}", sha):
                raise ValueError("invalid archive commit SHA")
            published = datetime.fromisoformat(revision["commit"]["committer"]["date"])
            if published.tzinfo is None or published.astimezone(SHANGHAI).date() != target:
                raise ValueError("archive publication date does not match the target in Beijing")
            url = f"https://raw.githubusercontent.com/{HISTORICAL_ARCHIVE_REPO}/{sha}/{path}"
            response = self.client.get(url)
            response.raise_for_status()
            archive = response.json()
            names = archive["list"]
            if archive["date"] != target.isoformat() or archive["language"] is not None:
                raise ValueError("archive target date or language does not match")
            if not isinstance(names, list):
                raise ValueError("invalid archive repository list")
        except (httpx.HTTPError, KeyError, ValueError, TypeError, IndexError) as exc:
            raise SourceError(f"榜期 {target} 的历史归档读取失败：{exc}") from exc

        valid = list(
            dict.fromkeys(
                name for name in names if isinstance(name, str) and _valid_repo_href(f"/{name}")
            )
        )[:10]
        if not valid:
            raise SourceError(f"榜期 {target} 的历史归档没有有效仓库")
        entries = [
            TrendingEntry(rank, name, f"https://github.com/{name}")
            for rank, name in enumerate(valid, start=1)
        ]
        self.enricher.enrich(entries, include_stars=False)
        warnings = [f"本项目的快照缺失，使用[同日历史归档]({url})。归档未保存当时的 Star 数。"]
        if len(entries) < 10:
            warnings.append(f"本次仅获取到 {len(entries)} 个有效仓库")
        return SourceResult(
            entries=entries,
            source=HISTORICAL_ARCHIVE_REPO,
            fetched_at=published,
            basis="第三方保存的 GitHub Trending 滚动日榜，项目简介和语言使用当前信息",
            warnings=warnings,
        )


class JsonFallbackSource:
    def __init__(
        self,
        client: httpx.Client,
        max_age: timedelta,
        url: str = FALLBACK_TRENDING_URL,
    ) -> None:
        self.client = client
        self.max_age = max_age
        self.url = url

    def fetch(self, now: datetime) -> SourceResult:
        response = self.client.get(self.url)
        response.raise_for_status()
        try:
            data = response.json()
            published = parsedate_to_datetime(data["pubDate"])
            raw_items = data["items"]
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceError("Fallback source returned an invalid payload") from exc
        if published.tzinfo is None:
            published = published.replace(tzinfo=now.tzinfo)
        age = now - published.astimezone(now.tzinfo)
        if age < timedelta(0) or age > self.max_age:
            raise SourceError(f"Fallback source is stale: published {published.isoformat()}")
        entries: list[TrendingEntry] = []
        for item in raw_items:
            full_name = str(item.get("title", "")).strip("/")
            if not _valid_repo_href(f"/{full_name}"):
                continue
            entries.append(
                TrendingEntry(
                    rank=len(entries) + 1,
                    full_name=full_name,
                    url=item.get("url") or f"https://github.com/{full_name}",
                    original_description=item.get("description") or "",
                    chinese_description="",
                    language=item.get("language") or None,
                    stars=parse_count(item.get("stars")),
                    stars_today=parse_count(item.get("addStars")),
                )
            )
        if not entries:
            raise SourceError("Fallback source returned no valid repositories")
        return SourceResult(
            entries=entries,
            source="isboyjc/github-trending-api",
            fetched_at=now,
            warnings=["主数据源不可用，已使用备用源"],
        )


class SourceOrchestrator:
    def __init__(
        self,
        primary: TrendingSource,
        fallback: TrendingSource,
        enricher: GitHubRepositoryEnricher | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.enricher = enricher

    def fetch_top(self, now: datetime, *, limit: int = 10) -> SourceResult:
        errors: list[str] = []
        for source in (self.primary, self.fallback):
            try:
                result = source.fetch(now)
                valid = [
                    entry for entry in result.entries if _valid_repo_href(f"/{entry.full_name}")
                ]
                valid = valid[:limit]
                for rank, entry in enumerate(valid, start=1):
                    entry.rank = rank
                if self.enricher:
                    valid = self.enricher.enrich(valid)
                result.entries = valid
                result.warnings = list(result.warnings or [])
                if len(valid) < limit:
                    result.warnings.append(f"本次仅获取到 {len(valid)} 个有效仓库")
                if not valid:
                    raise SourceError("Source returned no valid repositories")
                return result
            except (httpx.HTTPError, SourceError, ValueError) as exc:
                errors.append(f"{type(source).__name__}: {exc}")
                LOGGER.warning("Trending source failed: %s", errors[-1])
        raise SourceError("All trending sources failed: " + "; ".join(errors))

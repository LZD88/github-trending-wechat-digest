from __future__ import annotations

from dataclasses import dataclass

from github_trending_wechat.models import DigestSnapshot, TrendingEntry
from github_trending_wechat.scheduling import SHANGHAI
from github_trending_wechat.sources import HISTORICAL_ARCHIVE_REPO


@dataclass(frozen=True, slots=True)
class RenderedDigest:
    title: str
    segments: list[str]


def render_digest(
    snapshot: DigestSnapshot,
    *,
    max_chars: int = 12_000,
    resend: bool = False,
) -> RenderedDigest:
    prefix = "【补发】" if resend else ""
    title = f"{prefix}GitHub 热榜 Top {len(snapshot.entries)} · {snapshot.target_date.isoformat()}"
    fetched = snapshot.fetched_at.astimezone(SHANGHAI).strftime("%Y-%m-%d %H:%M %Z")
    time_label = "归档时间" if snapshot.source == HISTORICAL_ARCHIVE_REPO else "抓取时间"
    header_lines = [
        f"# {title}",
        "",
        f"> {time_label}：{fetched}",
        f"> 数据口径：{snapshot.basis}",
    ]
    if snapshot.warnings:
        header_lines.extend([f"> ⚠️ {warning}" for warning in snapshot.warnings])
    header = "\n".join(header_lines)
    blocks = [_render_entry(entry) for entry in snapshot.entries]
    if not blocks:
        blocks = ["本次没有可展示的有效仓库。"]

    raw_segments: list[str] = []
    current: list[str] = []
    for block in blocks:
        candidate = "\n\n".join([header, *current, block])
        if len(candidate) <= max_chars:
            current.append(block)
            continue
        if not current:
            raise ValueError("a single project block exceeds the message limit")
        raw_segments.append("\n\n".join([header, *current]))
        current = [block]
        if len("\n\n".join([header, block])) > max_chars:
            raise ValueError("a single project block exceeds the message limit")
    if current:
        raw_segments.append("\n\n".join([header, *current]))

    if len(raw_segments) == 1:
        return RenderedDigest(title=title, segments=raw_segments)
    total = len(raw_segments)
    segments = [
        f"{segment}\n\n---\n第 {index}/{total} 段" for index, segment in enumerate(raw_segments, 1)
    ]
    return RenderedDigest(title=title, segments=segments)


def _render_entry(entry: TrendingEntry) -> str:
    description = entry.chinese_description or entry.original_description or "暂无项目简介"
    language = entry.language or "暂无数据"
    stars = f"{entry.stars:,}" if entry.stars is not None else "暂无数据"
    added = f"+{entry.stars_today:,}" if entry.stars_today is not None else "暂无数据"
    return "\n".join(
        [
            f"## {entry.rank}. [{entry.full_name}]({entry.url})",
            description,
            f"- 语言：`{language}`",
            f"- 总 Star：⭐ {stars}",
            f"- 日榜新增：⭐ {added}",
        ]
    )

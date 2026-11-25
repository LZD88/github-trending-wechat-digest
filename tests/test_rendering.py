from datetime import UTC, date, datetime

import pytest

from github_trending_wechat.models import DigestSnapshot, TrendingEntry
from github_trending_wechat.rendering import render_digest


def make_snapshot(count: int, description: str = "中文简介") -> DigestSnapshot:
    return DigestSnapshot(
        target_date=date(2026, 11, 24),
        fetched_at=datetime(2026, 11, 25, tzinfo=UTC),
        source="github",
        basis="GitHub daily 滚动榜快照",
        entries=[
            TrendingEntry(
                rank=i,
                full_name=f"owner/repo-{i}",
                url=f"https://github.com/owner/repo-{i}",
                original_description="English",
                chinese_description=description,
                language="Python",
                stars=1000 + i,
                stars_today=10 + i,
            )
            for i in range(1, count + 1)
        ],
    )


def test_render_single_message_contains_required_fields_and_links() -> None:
    rendered = render_digest(make_snapshot(2))

    assert len(rendered.segments) == 1
    content = rendered.segments[0]
    assert "2026-11-24" in rendered.title
    assert "数据口径" in content
    assert "owner/repo-1" in content
    assert "https://github.com/owner/repo-1" in content
    assert "日榜新增" in content


def test_render_splits_only_between_complete_project_blocks() -> None:
    rendered = render_digest(make_snapshot(4, description="说明" * 30), max_chars=430)

    assert len(rendered.segments) > 1
    combined = "\n".join(rendered.segments)
    for index in range(1, 5):
        assert combined.count(f"owner/repo-{index}") == 2  # link text and URL
    assert "第 1/" in rendered.segments[0]
    assert f"第 {len(rendered.segments)}/{len(rendered.segments)} 段" in rendered.segments[-1]


def test_render_marks_manual_resend() -> None:
    rendered = render_digest(make_snapshot(1), resend=True)

    assert rendered.title.startswith("【补发】")


def test_render_rejects_single_block_larger_than_limit_without_truncating() -> None:
    with pytest.raises(ValueError, match="single project block"):
        render_digest(make_snapshot(1, description="长" * 1000), max_chars=200)

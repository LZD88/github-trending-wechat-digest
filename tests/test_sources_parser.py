from pathlib import Path

from github_trending_wechat.sources import parse_trending_html


def test_parse_trending_html_preserves_order_and_counts() -> None:
    html = Path("tests/fixtures/github_trending.html").read_text(encoding="utf-8")

    entries = parse_trending_html(html)

    assert [entry.full_name for entry in entries] == ["alpha/one", "beta/two"]
    assert [entry.rank for entry in entries] == [1, 2]
    assert entries[0].original_description == "First project"
    assert entries[0].language == "Python"
    assert entries[0].stars == 1234
    assert entries[0].stars_today == 321
    assert entries[1].stars_today == 7


def test_parse_trending_html_skips_invalid_repository_identity() -> None:
    html = '<article class="Box-row"><h2><a href="/owner/repo/issues">bad</a></h2></article>'

    assert parse_trending_html(html) == []

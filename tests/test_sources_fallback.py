from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from github_trending_wechat.sources import (
    FALLBACK_TRENDING_URL,
    JsonFallbackSource,
    SourceError,
)


def payload(pub_date: str) -> dict[str, object]:
    return {
        "pubDate": pub_date,
        "items": [
            {
                "title": "owner/repo",
                "url": "https://github.com/owner/repo",
                "description": "Description",
                "language": "Python",
                "stars": "1,234",
                "addStars": "56",
            }
        ],
    }


@respx.mock
def test_fallback_accepts_fresh_payload() -> None:
    now = datetime(2026, 11, 25, 0, 0, tzinfo=UTC)
    respx.get(FALLBACK_TRENDING_URL).mock(
        return_value=httpx.Response(200, json=payload("Tue, 24 Nov 2026 23:00:00 GMT"))
    )

    result = JsonFallbackSource(httpx.Client(), timedelta(hours=12)).fetch(now)

    assert result.source == "isboyjc/github-trending-api"
    assert result.entries[0].full_name == "owner/repo"
    assert result.entries[0].stars == 1234
    assert result.entries[0].stars_today == 56


@respx.mock
def test_fallback_rejects_stale_payload() -> None:
    now = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
    respx.get(FALLBACK_TRENDING_URL).mock(
        return_value=httpx.Response(200, json=payload("Tue, 24 Nov 2026 00:00:00 GMT"))
    )

    with pytest.raises(SourceError, match="stale"):
        JsonFallbackSource(httpx.Client(), timedelta(hours=12)).fetch(now)


@respx.mock
def test_fallback_rejects_invalid_payload() -> None:
    now = datetime(2026, 11, 25, tzinfo=UTC)
    respx.get(FALLBACK_TRENDING_URL).mock(
        return_value=httpx.Response(200, json={"pubDate": "not-a-date"})
    )

    with pytest.raises(SourceError, match="invalid payload"):
        JsonFallbackSource(httpx.Client(), timedelta(hours=12)).fetch(now)

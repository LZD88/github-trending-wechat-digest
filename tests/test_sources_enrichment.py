import httpx
import respx

from github_trending_wechat.models import TrendingEntry
from github_trending_wechat.sources import GitHubRepositoryEnricher


@respx.mock
def test_enricher_uses_token_and_updates_metadata() -> None:
    route = respx.get("https://api.github.com/repos/owner/repo").mock(
        return_value=httpx.Response(
            200,
            json={
                "description": "Authoritative description",
                "language": "Go",
                "stargazers_count": 999,
            },
        )
    )
    entry = TrendingEntry(1, "owner/repo", "https://github.com/owner/repo")
    client = httpx.Client()

    result = GitHubRepositoryEnricher(client, "github-token").enrich([entry])

    assert result[0].original_description == "Authoritative description"
    assert result[0].language == "Go"
    assert result[0].stars == 999
    assert route.calls[0].request.headers["authorization"] == "Bearer github-token"


@respx.mock
def test_enricher_preserves_existing_values_when_fields_are_missing() -> None:
    respx.get("https://api.github.com/repos/owner/repo").mock(
        return_value=httpx.Response(200, json={"description": None, "language": None})
    )
    entry = TrendingEntry(
        1,
        "owner/repo",
        "https://github.com/owner/repo",
        original_description="Original",
        language="Rust",
        stars=50,
    )

    result = GitHubRepositoryEnricher(httpx.Client()).enrich([entry])

    assert result[0].original_description == "Original"
    assert result[0].language == "Rust"
    assert result[0].stars == 50


@respx.mock
def test_enricher_degrades_on_api_failure_without_dropping_entry() -> None:
    respx.get("https://api.github.com/repos/owner/repo").mock(
        return_value=httpx.Response(503, text="unavailable")
    )
    entry = TrendingEntry(1, "owner/repo", "https://github.com/owner/repo", stars=10)

    result = GitHubRepositoryEnricher(httpx.Client()).enrich([entry])

    assert result == [entry]
    assert result[0].stars == 10

import json

import httpx
import pytest
import respx

from github_trending_wechat.models import TrendingEntry
from github_trending_wechat.summarizer import MYMEMORY_URL, ChineseSummarizer, contains_chinese


def entry(description: str) -> TrendingEntry:
    return TrendingEntry(1, "owner/repo", "https://github.com/owner/repo", description)


def test_contains_chinese_and_preserves_chinese_description() -> None:
    item = entry("这是中文项目简介")

    warnings = ChineseSummarizer(httpx.Client()).apply([item])

    assert contains_chinese(item.chinese_description)
    assert item.chinese_description == item.original_description
    assert warnings == []


@respx.mock
def test_batch_summarizes_english_descriptions() -> None:
    route = respx.post("https://summary.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"summaries": ["用于构建示例应用的工具。", "一个轻量测试框架。"]},
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )
    )
    items = [entry("Tool for building examples"), entry("A lightweight test framework")]

    warnings = ChineseSummarizer(
        httpx.Client(), api_base="https://summary.test/v1", api_key="secret"
    ).apply(items)

    assert [item.chinese_description for item in items] == [
        "用于构建示例应用的工具。",
        "一个轻量测试框架。",
    ]
    assert warnings == []
    assert len(route.calls) == 1


@respx.mock
def test_summary_failure_falls_back_to_original() -> None:
    respx.post("https://summary.test/v1/chat/completions").mock(
        return_value=httpx.Response(503, text="unavailable")
    )
    item = entry("Original English description")

    warnings = ChineseSummarizer(
        httpx.Client(), api_base="https://summary.test/v1", api_key="secret"
    ).apply([item])

    assert item.chinese_description == "Original English description"
    assert warnings


@respx.mock
def test_non_chinese_model_output_is_rejected() -> None:
    respx.post("https://summary.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"summaries":["English only"]}'}}]},
        )
    )
    item = entry("Original English description")

    ChineseSummarizer(httpx.Client(), api_base="https://summary.test/v1", api_key="secret").apply(
        [item]
    )

    assert item.chinese_description == item.original_description


@respx.mock
def test_fenced_model_response_keeps_valid_translations() -> None:
    respx.post("https://summary.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '```json\n{"summaries":["轻量测试框架。",null]}\n```'}}
                ]
            },
        )
    )
    items = [entry("Test framework"), entry("Another project")]

    warnings = ChineseSummarizer(
        httpx.Client(), api_base="https://summary.test/v1", api_key="secret"
    ).apply(items)

    assert [item.chinese_description for item in items] == ["轻量测试框架。", "Another project"]
    assert warnings


@respx.mock
def test_non_json_gateway_response_uses_public_translation_without_auth() -> None:
    respx.post("https://summary.test/v1/chat/completions").respond(200, text="OK")
    fallback = respx.get(MYMEMORY_URL).respond(
        200, json={"responseStatus": 200, "responseData": {"translatedText": "示例工具"}}
    )
    item = entry("Example tool")

    warnings = ChineseSummarizer(
        httpx.Client(), api_base="https://summary.test/v1", api_key="secret", public_fallback=True
    ).apply([item])

    assert item.chinese_description == "示例工具"
    assert warnings == []
    request = fallback.calls[0].request
    assert request.url.params["q"] == "Example tool"
    assert "authorization" not in request.headers


@respx.mock
def test_explicit_model_refusal_does_not_call_another_provider() -> None:
    respx.post("https://summary.test/v1/chat/completions").respond(
        200, json={"choices": [{"finish_reason": "content_filter", "message": {"content": None}}]}
    )
    item = entry("Example tool")

    warnings = ChineseSummarizer(
        httpx.Client(), api_base="https://summary.test/v1", api_key="secret", public_fallback=True
    ).apply([item])

    assert "暂无法转换为中文" in item.chinese_description
    assert warnings


@respx.mock
def test_failed_public_translation_keeps_original_and_records_cause(
    caplog: pytest.LogCaptureFixture,
) -> None:
    respx.get(MYMEMORY_URL).respond(429)
    item = entry("Example tool")

    warnings = ChineseSummarizer(httpx.Client(), public_fallback=True).apply([item])

    assert item.chinese_description == "Example tool"
    assert warnings == ["1 个项目的中文简介暂不可用，已保留英文原文"]
    assert "HTTP 429" in caplog.text

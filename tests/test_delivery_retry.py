import httpx
import respx

from github_trending_wechat.delivery import ServerChanProvider


@respx.mock
def test_temporary_failure_retries_with_backoff_then_succeeds() -> None:
    route = respx.post("https://sctapi.ftqq.com/SCT_TEST.send").mock(
        side_effect=[
            httpx.Response(503, text="unavailable"),
            httpx.Response(200, json={"code": 0, "data": {"pushid": "ok"}}),
        ]
    )
    sleeps: list[float] = []
    provider = ServerChanProvider(
        httpx.Client(), "SCT_TEST", sleep=sleeps.append, jitter=lambda: 0.25
    )

    result = provider.send("标题", ["正文"])

    assert result.success is True
    assert result.attempt_count == 2
    assert len(route.calls) == 2
    assert sleeps == [1.25]


@respx.mock
def test_rate_limit_is_retryable() -> None:
    route = respx.post("https://sctapi.ftqq.com/SCT_TEST.send").mock(
        side_effect=[
            httpx.Response(429, text="slow down"),
            httpx.Response(200, json={"code": 0, "data": {"pushid": "ok"}}),
        ]
    )
    provider = ServerChanProvider(
        httpx.Client(), "SCT_TEST", sleep=lambda _: None, jitter=lambda: 0
    )

    result = provider.send("标题", ["正文"])

    assert result.success is True
    assert len(route.calls) == 2


@respx.mock
def test_timeout_is_retryable() -> None:
    route = respx.post("https://sctapi.ftqq.com/SCT_TEST.send").mock(
        side_effect=[
            httpx.ConnectTimeout("timed out"),
            httpx.Response(200, json={"code": 0, "data": {"pushid": "ok"}}),
        ]
    )
    provider = ServerChanProvider(
        httpx.Client(), "SCT_TEST", sleep=lambda _: None, jitter=lambda: 0
    )

    result = provider.send("标题", ["正文"])

    assert result.success is True
    assert result.attempt_count == 2
    assert len(route.calls) == 2


@respx.mock
def test_authentication_failure_is_not_retried() -> None:
    route = respx.post("https://sctapi.ftqq.com/SCT_TEST.send").mock(
        return_value=httpx.Response(401, text="bad key")
    )
    sleeps: list[float] = []
    provider = ServerChanProvider(httpx.Client(), "SCT_TEST", sleep=sleeps.append)

    result = provider.send("标题", ["正文"])

    assert result.success is False
    assert result.error_category == "authentication"
    assert result.attempt_count == 1
    assert len(route.calls) == 1
    assert sleeps == []


@respx.mock
def test_retries_stop_after_three_attempts() -> None:
    route = respx.post("https://sctapi.ftqq.com/SCT_TEST.send").mock(
        return_value=httpx.Response(503, text="unavailable")
    )
    sleeps: list[float] = []
    provider = ServerChanProvider(httpx.Client(), "SCT_TEST", sleep=sleeps.append, jitter=lambda: 0)

    result = provider.send("标题", ["正文"])

    assert result.success is False
    assert result.error_category == "temporary"
    assert result.attempt_count == 3
    assert len(route.calls) == 3
    assert sleeps == [1, 2]

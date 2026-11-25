import httpx
import pytest
import respx

from github_trending_wechat.delivery import DeliveryError, ServerChanProvider


@respx.mock
def test_serverchan_success_returns_message_id_and_posts_form() -> None:
    route = respx.post("https://sctapi.ftqq.com/SCT_TEST.send").mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"pushid": "push-1"}})
    )
    provider = ServerChanProvider(httpx.Client(), "SCT_TEST")

    result = provider.send("测试标题", ["测试正文"])

    assert result.success is True
    assert result.message_ids == ["push-1"]
    assert result.attempt_count == 1
    assert "title=" in route.calls[0].request.content.decode()
    assert len(provider.recipient_fingerprint) == 16
    assert "SCT_TEST" not in provider.recipient_fingerprint


def test_serverchan_validates_title_and_body_limits_before_request() -> None:
    provider = ServerChanProvider(httpx.Client(), "SCT_TEST", max_title_chars=4, max_body_chars=5)

    with pytest.raises(DeliveryError, match="title"):
        provider.send("标题太长了", ["正文"])
    with pytest.raises(DeliveryError, match="body"):
        provider.send("标题", ["正文真的太长"])


@respx.mock
def test_serverchan_sends_all_segments_in_order() -> None:
    route = respx.post("https://sctapi.ftqq.com/SCT_TEST.send").mock(
        side_effect=[
            httpx.Response(200, json={"code": 0, "data": {"pushid": "one"}}),
            httpx.Response(200, json={"code": 0, "data": {"pushid": "two"}}),
        ]
    )

    result = ServerChanProvider(httpx.Client(), "SCT_TEST").send("标题", ["一", "二"])

    assert result.message_ids == ["one", "two"]
    assert len(route.calls) == 2

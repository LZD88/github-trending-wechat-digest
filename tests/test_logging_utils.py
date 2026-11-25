import io
import logging

from github_trending_wechat.logging_utils import SecretRedactionFilter, redact_text


def test_redact_text_hides_configured_and_common_secret_forms() -> None:
    text = (
        "sendkey=SCT123 api_key=summary-secret "
        "Authorization: Bearer github-secret https://sctapi.ftqq.com/SCT123.send"
    )

    output = redact_text(text, ["SCT123", "summary-secret", "github-secret"])

    assert "SCT123" not in output
    assert "summary-secret" not in output
    assert "github-secret" not in output
    assert output.count("[REDACTED]") >= 3


def test_logging_filter_redacts_arguments_after_formatting() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SecretRedactionFilter(["actual-secret"]))
    logger = logging.getLogger("redaction-test")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.info("Authorization=%s", "actual-secret")

    output = stream.getvalue()
    assert "actual-secret" not in output
    assert "[REDACTED]" in output

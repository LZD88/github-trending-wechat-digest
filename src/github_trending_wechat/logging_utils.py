from __future__ import annotations

import logging
import re
from collections.abc import Iterable


class SecretRedactionFilter(logging.Filter):
    """Redact configured secrets and common authorization forms from log records."""

    def __init__(self, secrets: Iterable[str | None] = ()) -> None:
        super().__init__()
        self._secrets = tuple(secret for secret in secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        message = redact_text(message, self._secrets)
        record.msg = message
        record.args = ()
        return True


def redact_text(text: str, secrets: Iterable[str | None] = ()) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = re.sub(
        r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)([^\s,;]+)",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)((?:sendkey|api[_-]?key|token)\s*[:=]\s*)([^\s,;&]+)",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(https?://sctapi\.ftqq\.com/)([^/.\s]+)(\.send)",
        r"\1[REDACTED]\3",
        redacted,
    )
    return redacted


def configure_logging(*, secrets: Iterable[str | None] = (), level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(SecretRedactionFilter(secrets))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

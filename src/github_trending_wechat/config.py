from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Raised when runtime configuration is invalid."""


SUPPORTED_PROVIDERS = ("serverchan",)


@dataclass(frozen=True, slots=True)
class Settings:
    provider: str = "serverchan"
    serverchan_sendkey: str | None = None
    github_token: str | None = None
    summary_api_base: str | None = None
    summary_api_key: str | None = None
    summary_model: str = "gpt-4o-mini"
    summary_public_fallback: bool = False
    data_dir: Path = Path("data")
    http_timeout_seconds: float = 20.0
    fallback_max_age_hours: int = 12
    serverchan_api_base: str = "https://sctapi.ftqq.com"

    @property
    def summary_enabled(self) -> bool:
        return bool(self.summary_api_key)

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        require_delivery: bool = False,
    ) -> Settings:
        env = os.environ if environ is None else environ
        provider = env.get("DELIVERY_PROVIDER", "serverchan").strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            supported = ", ".join(SUPPORTED_PROVIDERS)
            raise ConfigError(f"Unsupported DELIVERY_PROVIDER {provider!r}; choose: {supported}")

        sendkey = _clean(env.get("SERVERCHAN_SENDKEY"))
        if require_delivery and provider == "serverchan" and not sendkey:
            raise ConfigError("SERVERCHAN_SENDKEY is required for delivery")

        summary_key = _clean(env.get("SUMMARY_API_KEY"))
        summary_base = _clean(env.get("SUMMARY_API_BASE"))
        summary_model = _clean(env.get("SUMMARY_MODEL")) or "gpt-4o-mini"
        github_token = _clean(env.get("GITHUB_TOKEN"))
        use_github_models = env.get("SUMMARY_USE_GITHUB_MODELS") == "true"
        summary_public_fallback = use_github_models and not summary_key
        if not summary_key and use_github_models:
            summary_key = github_token
            summary_base = "https://models.github.ai/inference" if github_token else None
            summary_model = "openai/gpt-4.1-mini"
        elif summary_base and not summary_key:
            raise ConfigError("SUMMARY_API_KEY is required when SUMMARY_API_BASE is set")
        if summary_key and not summary_base:
            summary_base = "https://api.openai.com/v1"

        timeout = _float_value(env, "HTTP_TIMEOUT_SECONDS", 20.0, minimum=0.1)
        max_age = _int_value(env, "FALLBACK_MAX_AGE_HOURS", 12, minimum=1)

        return cls(
            provider=provider,
            serverchan_sendkey=sendkey,
            github_token=github_token,
            summary_api_base=summary_base,
            summary_api_key=summary_key,
            summary_model=summary_model,
            summary_public_fallback=summary_public_fallback,
            data_dir=Path(env.get("DATA_DIR", "data")),
            http_timeout_seconds=timeout,
            fallback_max_age_hours=max_age,
            serverchan_api_base=env.get("SERVERCHAN_API_BASE", "https://sctapi.ftqq.com").rstrip(
                "/"
            ),
        )


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _float_value(env: Mapping[str, str], name: str, default: float, *, minimum: float) -> float:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}")
    return value


def _int_value(env: Mapping[str, str], name: str, default: int, *, minimum: int) -> int:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}")
    return value

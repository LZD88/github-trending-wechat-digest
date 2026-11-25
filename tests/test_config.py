from pathlib import Path

import pytest

from github_trending_wechat.config import ConfigError, Settings


def test_preview_configuration_does_not_require_sendkey() -> None:
    settings = Settings.from_env({})

    assert settings.provider == "serverchan"
    assert settings.serverchan_sendkey is None
    assert settings.data_dir == Path("data")


def test_delivery_requires_serverchan_sendkey() -> None:
    with pytest.raises(ConfigError, match="SERVERCHAN_SENDKEY"):
        Settings.from_env({}, require_delivery=True)


def test_unknown_provider_lists_supported_values() -> None:
    with pytest.raises(ConfigError, match="serverchan"):
        Settings.from_env({"DELIVERY_PROVIDER": "mystery"})


def test_summary_key_enables_default_openai_compatible_endpoint() -> None:
    settings = Settings.from_env({"SUMMARY_API_KEY": "secret"})

    assert settings.summary_enabled is True
    assert settings.summary_api_base == "https://api.openai.com/v1"
    assert settings.summary_model == "gpt-4o-mini"


def test_summary_base_without_key_is_rejected() -> None:
    with pytest.raises(ConfigError, match="SUMMARY_API_KEY"):
        Settings.from_env({"SUMMARY_API_BASE": "https://example.test/v1"})


def test_github_models_token_is_only_used_with_the_fixed_endpoint() -> None:
    settings = Settings.from_env(
        {
            "SUMMARY_USE_GITHUB_MODELS": "true",
            "GITHUB_TOKEN": "job-token",
            "SUMMARY_API_BASE": "https://summary.example/v1",
            "SUMMARY_MODEL": "custom-model",
        }
    )

    assert settings.summary_api_key == "job-token"
    assert settings.summary_api_base == "https://models.github.ai/inference"
    assert settings.summary_model == "openai/gpt-4.1-mini"
    assert settings.summary_public_fallback is True


def test_custom_summary_service_retains_precedence_over_github_models() -> None:
    settings = Settings.from_env(
        {
            "SUMMARY_USE_GITHUB_MODELS": "true",
            "GITHUB_TOKEN": "job-token",
            "SUMMARY_API_KEY": "translation-key",
            "SUMMARY_API_BASE": "https://summary.example/v1",
            "SUMMARY_MODEL": "custom-model",
        }
    )

    assert settings.summary_api_key == "translation-key"
    assert settings.summary_api_base == "https://summary.example/v1"
    assert settings.summary_model == "custom-model"
    assert settings.summary_public_fallback is False


def test_numeric_configuration_is_validated() -> None:
    with pytest.raises(ConfigError, match="HTTP_TIMEOUT_SECONDS"):
        Settings.from_env({"HTTP_TIMEOUT_SECONDS": "0"})

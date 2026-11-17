from pathlib import Path

import pytest

from api.app.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def _env_example_names() -> set[str]:
    return {
        line.split("=", 1)[0].strip()
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _env_example_names():
        monkeypatch.delenv(name, raising=False)


@pytest.mark.usefixtures("clean_env")
def test_defaults_without_env_file() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.model_default == "claude-haiku-5-5"
    assert settings.model_eval == "claude-sonnet-5-5"
    assert settings.embeddings_model == "voyage-4-lite"
    assert settings.anthropic_api_key is None
    assert settings.ask_rate_limit_per_hour == 10
    assert settings.ask_daily_spend_cap_usd == 0.50


@pytest.mark.usefixtures("clean_env")
def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_DEFAULT", "some-other-model")
    monkeypatch.setenv("ASK_RATE_LIMIT_PER_HOUR", "3")

    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.model_default == "some-other-model"
    assert settings.ask_rate_limit_per_hour == 3


def test_settings_match_env_example() -> None:
    """config.py and .env.example list the same variables. Web-only ones are skipped."""
    api_names = {n for n in _env_example_names() if not n.startswith("NEXT_PUBLIC_")}

    assert api_names == {field.upper() for field in Settings.model_fields}

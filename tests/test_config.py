from __future__ import annotations

from app.config import PROJECT_ROOT, Settings


def test_deepseek_provider_uses_openai_compatible_defaults(monkeypatch, tmp_path):
    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env(
        llm_provider="deepseek",
        database_path=tmp_path / "test.db",
        seed_dir=PROJECT_ROOT / "app" / "data" / "seed",
    )

    assert settings.llm_provider == "deepseek"
    assert settings.llm_base_url == "https://api.deepseek.com/v1"
    assert settings.llm_model == "deepseek-chat"
    assert settings.llm_max_tokens == 900


def test_unknown_provider_falls_back_to_compatible_defaults(monkeypatch, tmp_path):
    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env(
        llm_provider="custom-vendor",
        database_path=tmp_path / "test.db",
        seed_dir=PROJECT_ROOT / "app" / "data" / "seed",
    )

    assert settings.llm_provider == "custom-vendor"
    assert settings.llm_base_url == "https://api.openai.com/v1"
    assert settings.llm_model == "gpt-4o-mini"

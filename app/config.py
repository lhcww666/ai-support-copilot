from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LLM_PROVIDER_DEFAULTS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
    "openai-compatible": ("https://api.openai.com/v1", "gpt-4o-mini"),
}


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "AI Support Copilot"
    app_env: str = "development"
    app_secret: str = "dev-only-change-me"
    database_path: Path = PROJECT_ROOT / "data" / "support_copilot.db"
    seed_dir: Path = PROJECT_ROOT / "app" / "data" / "seed"
    token_ttl_seconds: int = 24 * 60 * 60
    max_upload_bytes: int = 2 * 1024 * 1024
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 30
    llm_temperature: float = 0.1
    llm_max_tokens: int = 900
    query_rewrite_enabled: bool = True
    query_rewrite_max_tokens: int = 160
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    conversation_history_limit: int = 6
    retrieval_limit: int = 4
    admin_password: str = "admin123"
    operator_password: str = "operator123"
    viewer_password: str = "viewer123"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key.strip())

    @classmethod
    def from_env(cls, **overrides: object) -> Settings:
        load_dotenv(PROJECT_ROOT / ".env")
        defaults = cls()
        provider = str(overrides.get("llm_provider") or os.getenv("LLM_PROVIDER", "openai"))
        provider = provider.strip().lower()
        provider_base_url, provider_model = LLM_PROVIDER_DEFAULTS.get(
            provider,
            LLM_PROVIDER_DEFAULTS["openai-compatible"],
        )
        values: dict[str, object] = {
            "app_name": os.getenv("APP_NAME", defaults.app_name),
            "app_env": os.getenv("APP_ENV", defaults.app_env),
            "app_secret": os.getenv("APP_SECRET", defaults.app_secret),
            "database_path": Path(
                os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "support_copilot.db"))
            ),
            "seed_dir": Path(
                os.getenv("SEED_DIR", str(PROJECT_ROOT / "app" / "data" / "seed"))
            ),
            "token_ttl_seconds": int(os.getenv("TOKEN_TTL_SECONDS", "86400")),
            "max_upload_bytes": int(os.getenv("MAX_UPLOAD_BYTES", str(2 * 1024 * 1024))),
            "llm_provider": provider,
            "llm_api_key": os.getenv("LLM_API_KEY", ""),
            "llm_base_url": os.getenv("LLM_BASE_URL", provider_base_url),
            "llm_model": os.getenv("LLM_MODEL", provider_model),
            "llm_timeout_seconds": int(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
            "llm_temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
            "llm_max_tokens": int(os.getenv("LLM_MAX_TOKENS", "900")),
            "query_rewrite_enabled": os.getenv("QUERY_REWRITE_ENABLED", "true").lower()
            in {"1", "true", "yes"},
            "query_rewrite_max_tokens": int(os.getenv("QUERY_REWRITE_MAX_TOKENS", "160")),
            "embedding_api_key": os.getenv("EMBEDDING_API_KEY", ""),
            "embedding_base_url": os.getenv(
                "EMBEDDING_BASE_URL", "https://api.openai.com/v1"
            ),
            "embedding_model": os.getenv(
                "EMBEDDING_MODEL", "text-embedding-3-small"
            ),
            "conversation_history_limit": int(
                os.getenv("CONVERSATION_HISTORY_LIMIT", "6")
            ),
            "retrieval_limit": int(os.getenv("RETRIEVAL_LIMIT", "4")),
            "admin_password": os.getenv("DEMO_ADMIN_PASSWORD", "admin123"),
            "operator_password": os.getenv("DEMO_OPERATOR_PASSWORD", "operator123"),
            "viewer_password": os.getenv("DEMO_VIEWER_PASSWORD", "viewer123"),
        }
        values.update(overrides)
        return cls(**values)

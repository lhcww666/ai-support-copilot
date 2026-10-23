from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT, Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings.from_env(
        database_path=tmp_path / "test.db",
        seed_dir=PROJECT_ROOT / "app" / "data" / "seed",
        app_secret="test-secret-with-enough-length",
        llm_api_key="",
        embedding_api_key="",
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def login(client: TestClient, username: str) -> dict:
    passwords = {
        "admin": "admin123",
        "operator": "operator123",
        "viewer": "viewer123",
    }
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": passwords[username]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def auth_headers(client: TestClient, username: str) -> dict[str, str]:
    token = login(client, username)["access_token"]
    return {"Authorization": f"Bearer {token}"}

from __future__ import annotations

from tests.conftest import auth_headers, login


def test_health_and_seed_documents(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["documents"] == 5
    assert response.json()["llm_mode"] == "offline-rule"


def test_login_and_me(client):
    token = login(client, "operator")

    assert token["user"]["role"] == "operator"
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "operator"


def test_invalid_login_is_rejected(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_unauthenticated_request_is_rejected(client):
    assert client.get("/api/v1/documents").status_code == 401


def test_document_visibility_follows_role(client):
    viewer_docs = client.get(
        "/api/v1/documents", headers=auth_headers(client, "viewer")
    ).json()
    operator_docs = client.get(
        "/api/v1/documents", headers=auth_headers(client, "operator")
    ).json()
    admin_docs = client.get(
        "/api/v1/documents", headers=auth_headers(client, "admin")
    ).json()

    assert len(viewer_docs) == 2
    assert len(operator_docs) == 4
    assert len(admin_docs) == 5


def test_admin_can_create_and_delete_text_document(client):
    headers = auth_headers(client, "admin")
    created = client.post(
        "/api/v1/documents/text",
        headers=headers,
        json={
            "title": "新品发布流程",
            "content": "新品发布前需要完成安全评审、价格审批和客服话术培训。",
            "visibility": "internal",
        },
    )

    assert created.status_code == 200
    document_id = created.json()["id"]
    deleted = client.delete(f"/api/v1/documents/{document_id}", headers=headers)

    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_document_upload_validates_role_and_extension(client):
    viewer = auth_headers(client, "viewer")
    admin = auth_headers(client, "admin")

    forbidden = client.post(
        "/api/v1/documents/upload",
        headers=viewer,
        files={"file": ("note.md", b"hello world policy", "text/markdown")},
    )
    invalid = client.post(
        "/api/v1/documents/upload",
        headers=admin,
        files={"file": ("note.exe", b"not allowed", "application/octet-stream")},
    )

    assert forbidden.status_code == 403
    assert invalid.status_code == 400


def test_admin_can_upload_markdown(client):
    response = client.post(
        "/api/v1/documents/upload?visibility=public",
        headers=auth_headers(client, "admin"),
        files={
            "file": (
                "shipping-note.md",
                "# 包装规范\n\n易碎品必须使用双层纸箱和缓冲材料，外箱需要粘贴易碎标签。".encode(),
                "text/markdown",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["title"] == "shipping-note"
    assert response.json()["visibility"] == "public"

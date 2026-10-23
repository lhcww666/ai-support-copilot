from __future__ import annotations

from tests.conftest import auth_headers


def test_rag_evaluation_is_ten_of_ten(client):
    response = client.get(
        "/api/v1/evaluations/rag",
        headers=auth_headers(client, "admin"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["suite"] == "rag-retrieval"
    assert body["total"] == 10
    assert body["hits"] == 10
    assert body["pass_rate"] == 1.0


def test_evaluation_requires_admin(client):
    response = client.get(
        "/api/v1/evaluations/rag",
        headers=auth_headers(client, "operator"),
    )

    assert response.status_code == 403

from __future__ import annotations

import json

from tests.conftest import auth_headers


def test_rag_answer_returns_sources(client):
    response = client.post(
        "/api/v1/chat",
        headers=auth_headers(client, "viewer"),
        json={"query": "员工密码连续输错几次会锁定账号？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["planner"] == "local-rule"
    assert body["fallback"] is False
    assert body["sources"]
    assert any(source["title"] == "账号与密码策略" for source in body["sources"])
    assert "5 次" in body["answer"]


def test_operator_can_query_order_through_tool(client):
    response = client.post(
        "/api/v1/chat",
        headers=auth_headers(client, "operator"),
        json={"query": "查询订单 SO-1001 的物流状态"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "运输中" in body["answer"]
    assert body["tool_calls"][0]["name"] == "query_order_status"
    assert body["tool_calls"][0]["success"] is True


def test_viewer_order_query_is_blocked_by_tool(client):
    response = client.post(
        "/api/v1/chat",
        headers=auth_headers(client, "viewer"),
        json={"query": "查询订单 SO-1001 的物流状态"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "无权" in body["answer"]
    assert body["tool_calls"][0]["success"] is False


def test_ticket_draft_requires_confirmation_and_is_idempotent(client):
    headers = auth_headers(client, "operator")
    chat = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"query": "为登录失败创建高优先级工单"},
    )
    call = chat.json()["tool_calls"][0]
    draft_id = call["output"]["draft_id"]

    first = client.post(f"/api/v1/tickets/{draft_id}/confirm", headers=headers)
    second = client.post(f"/api/v1/tickets/{draft_id}/confirm", headers=headers)

    assert first.status_code == 200
    assert first.json()["status"] == "OPEN"
    assert second.json()["ticket_id"] == first.json()["ticket_id"]
    assert second.json()["idempotent"] is True


def test_viewer_cannot_confirm_ticket(client):
    admin_headers = auth_headers(client, "admin")
    draft = client.post(
        "/api/v1/tickets/drafts",
        headers=admin_headers,
        json={
            "title": "管理员创建",
            "description": "测试只读用户无法确认",
            "priority": "MEDIUM",
        },
    ).json()

    response = client.post(
        f"/api/v1/tickets/{draft['draft_id']}/confirm",
        headers=auth_headers(client, "viewer"),
    )

    assert response.status_code == 403


def test_sse_stream_contains_meta_sources_tokens_and_done(client):
    response = client.post(
        "/api/v1/chat/stream",
        headers=auth_headers(client, "viewer"),
        json={"query": "标准订单多久发货？"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    assert "event: meta" in text
    assert "event: sources" in text
    assert "event: token" in text
    assert "event: done" in text


def test_conversation_cannot_be_reused_by_another_user(client):
    first = client.post(
        "/api/v1/chat",
        headers=auth_headers(client, "viewer"),
        json={"query": "账号锁定多久？"},
    ).json()

    response = client.post(
        "/api/v1/chat",
        headers=auth_headers(client, "operator"),
        json={"query": "继续", "conversation_id": first["conversation_id"]},
    )

    assert response.status_code == 403


def test_direct_order_endpoint_and_audit_log(client):
    operator = auth_headers(client, "operator")
    order = client.get("/api/v1/orders/SO-1002", headers=operator)
    audit = client.get("/api/v1/admin/audit-logs", headers=auth_headers(client, "admin"))

    assert order.status_code == 200
    assert order.json()["status"] == "已签收"
    assert audit.status_code == 200
    assert any(item["action"] == "ORDER_QUERY" for item in audit.json())


def test_tool_output_is_json_serializable(client):
    response = client.post(
        "/api/v1/chat",
        headers=auth_headers(client, "operator"),
        json={"query": "SO-1003 发货了吗"},
    )
    output = response.json()["tool_calls"][0]["output"]

    assert json.loads(json.dumps(output, ensure_ascii=False))["order_id"] == "SO-1003"

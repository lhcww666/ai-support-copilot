from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.orders import OrderService
from app.security import AuthError, User
from app.tickets import TicketService


@dataclass(slots=True)
class ToolContext:
    user: User
    calls: list[dict[str, Any]] = field(default_factory=list)


_current_context: ContextVar[ToolContext | None] = ContextVar("tool_context", default=None)


@contextmanager
def tool_context(user: User) -> Iterator[list[dict[str, Any]]]:
    context = ToolContext(user=user)
    token = _current_context.set(context)
    try:
        yield context.calls
    finally:
        _current_context.reset(token)


def build_tools(order_service: OrderService, ticket_service: TicketService) -> list[BaseTool]:
    @tool
    def query_order_status(order_id: str) -> str:
        """按销售订单号查询状态、承运商、运单号和预计送达时间。"""
        context = _require_context()
        payload: dict[str, Any]
        try:
            payload = {"success": True, **order_service.get_status(context.user, order_id)}
        except AuthError as exc:
            payload = {"success": False, "code": "FORBIDDEN", "message": str(exc)}
        except LookupError as exc:
            payload = {"success": False, "code": "NOT_FOUND", "message": str(exc)}
        _record(context, "query_order_status", {"order_id": order_id}, payload)
        return json.dumps(payload, ensure_ascii=False)

    @tool
    def prepare_support_ticket(
        title: str,
        description: str,
        priority: str = "MEDIUM",
    ) -> str:
        """创建待人工确认的客服工单草稿；不会直接创建正式工单。"""
        context = _require_context()
        try:
            draft_id = ticket_service.prepare(
                context.user,
                title=title,
                description=description,
                priority=priority.upper(),
            )
            payload = {
                "success": True,
                "code": "CONFIRMATION_REQUIRED",
                "draft_id": draft_id,
                "message": "工单草稿已生成，必须由用户确认后才能创建正式工单",
            }
        except (AuthError, ValueError) as exc:
            payload = {"success": False, "code": "INVALID_REQUEST", "message": str(exc)}
        _record(
            context,
            "prepare_support_ticket",
            {"title": title, "description": description, "priority": priority},
            payload,
        )
        return json.dumps(payload, ensure_ascii=False)

    return [query_order_status, prepare_support_ticket]


def _require_context() -> ToolContext:
    context = _current_context.get()
    if context is None:
        raise RuntimeError("工具调用缺少用户上下文")
    return context


def _record(
    context: ToolContext,
    name: str,
    tool_input: dict[str, Any],
    output: dict[str, Any],
) -> None:
    context.calls.append(
        {
            "name": name,
            "input": tool_input,
            "output": output,
            "success": bool(output.get("success")),
        }
    )

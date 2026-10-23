from __future__ import annotations

from app.repositories import SqliteRepository
from app.security import AuthError, User


class TicketService:
    def __init__(self, repository: SqliteRepository) -> None:
        self.repository = repository

    def prepare(
        self,
        user: User,
        title: str,
        description: str,
        priority: str,
    ) -> str:
        if user.role == "viewer":
            raise AuthError("只读用户无权创建工单")
        if priority not in {"LOW", "MEDIUM", "HIGH"}:
            raise ValueError("工单优先级无效")
        return self.repository.create_ticket_draft(
            requester=user.username,
            title=title.strip(),
            description=description.strip(),
            priority=priority,
        )

    def confirm(self, user: User, draft_id: str) -> tuple[dict, bool]:
        if user.role == "viewer":
            raise AuthError("只读用户无权确认工单")
        ticket, idempotent = self.repository.confirm_ticket(draft_id, user.username)
        self.repository.audit(
            user.username,
            "TICKET_CONFIRM",
            str(ticket["ticket_id"]),
            "success",
            {"draft_id": draft_id, "idempotent": idempotent},
        )
        return ticket, idempotent

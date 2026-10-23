from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SqliteRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    visibility TEXT NOT NULL CHECK (visibility IN ('public','internal','admin')),
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );

                CREATE TABLE IF NOT EXISTS ticket_drafts (
                    draft_id TEXT PRIMARY KEY,
                    requester TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id TEXT PRIMARY KEY,
                    draft_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (draft_id) REFERENCES ticket_drafts(draft_id)
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def document_count(self) -> int:
        with self.connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0])

    def insert_document(
        self,
        title: str,
        content: str,
        visibility: str,
        created_by: str,
    ) -> str:
        document_id = str(uuid.uuid4())
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO documents(id,title,content,visibility,created_by,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (document_id, title, content, visibility, created_by, utc_now()),
            )
        return document_id

    def list_documents(self, visibilities: set[str]) -> list[dict[str, Any]]:
        if not visibilities:
            return []
        placeholders = ",".join("?" for _ in visibilities)
        query = (
            "SELECT id,title,content,visibility,created_by,created_at FROM documents "
            f"WHERE visibility IN ({placeholders}) ORDER BY created_at DESC"
        )
        with self.connection() as connection:
            return [dict(row) for row in connection.execute(query, tuple(visibilities))]

    def delete_document(self, document_id: str) -> bool:
        with self.connection() as connection:
            cursor = connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            return cursor.rowcount > 0

    def ensure_conversation(self, conversation_id: str, username: str) -> None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO conversations(id,user_id,created_at) VALUES(?,?,?)",
                    (conversation_id, username, utc_now()),
                )
            elif row["user_id"] != username:
                raise PermissionError("会话不属于当前用户")

    def add_message(
        self,
        conversation_id: str,
        username: str,
        role: str,
        content: str,
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO messages(conversation_id,user_id,role,content,created_at) "
                "VALUES(?,?,?,?,?)",
                (conversation_id, username, role, content, utc_now()),
            )

    def messages(self, conversation_id: str, username: str, limit: int) -> list[dict[str, str]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT role,content FROM messages WHERE conversation_id = ? AND user_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (conversation_id, username, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def create_ticket_draft(
        self,
        requester: str,
        title: str,
        description: str,
        priority: str,
    ) -> str:
        draft_id = f"DRF-{uuid.uuid4().hex[:10].upper()}"
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO ticket_drafts("
                "draft_id,requester,title,description,priority,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (draft_id, requester, title, description, priority, utc_now()),
            )
        return draft_id

    def ticket_draft(self, draft_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM ticket_drafts WHERE draft_id = ?", (draft_id,)
            ).fetchone()
        return dict(row) if row else None

    def confirm_ticket(self, draft_id: str, requester: str) -> tuple[dict[str, Any], bool]:
        with self.connection() as connection:
            draft = connection.execute(
                "SELECT * FROM ticket_drafts WHERE draft_id = ?", (draft_id,)
            ).fetchone()
            if draft is None:
                raise ValueError("工单草稿不存在")
            if draft["requester"] != requester:
                raise PermissionError("不能确认其他用户的工单草稿")
            existing = connection.execute(
                "SELECT * FROM tickets WHERE draft_id = ?", (draft_id,)
            ).fetchone()
            if existing is not None:
                return dict(existing), True
            ticket_id = f"TKT-{uuid.uuid4().hex[:10].upper()}"
            connection.execute(
                "INSERT INTO tickets(ticket_id,draft_id,title,status,created_at) "
                "VALUES(?,?,?,?,?)",
                (ticket_id, draft_id, draft["title"], "OPEN", utc_now()),
            )
            row = connection.execute(
                "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
            return dict(row), False

    def audit(
        self,
        username: str,
        action: str,
        resource: str,
        outcome: str,
        details: dict[str, Any] | str,
    ) -> None:
        encoded = details if isinstance(details, str) else json.dumps(details, ensure_ascii=False)
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO audit_logs(username,action,resource,outcome,details,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (username, action, resource, outcome, encoded, utc_now()),
            )

    def list_audit_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["details"] = json.loads(item["details"])
            except (TypeError, json.JSONDecodeError):
                pass
            items.append(item)
        return items

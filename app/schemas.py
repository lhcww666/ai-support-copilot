from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class UserResponse(BaseModel):
    username: str
    display_name: str
    role: Literal["viewer", "operator", "admin"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ChatRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)


class SourceResponse(BaseModel):
    document_id: str
    title: str
    visibility: str
    score: float
    snippet: str


class ToolCallResponse(BaseModel):
    name: str
    input: dict
    output: dict | str
    success: bool


class ChatResponse(BaseModel):
    conversation_id: str
    original_query: str
    retrieval_query: str
    query_rewritten: bool
    answer: str
    sources: list[SourceResponse]
    tool_calls: list[ToolCallResponse]
    planner: str
    fallback: bool


class DocumentResponse(BaseModel):
    id: str
    title: str
    visibility: Literal["public", "internal", "admin"]
    created_by: str
    created_at: str
    size: int


class DocumentTextRequest(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    content: str = Field(min_length=10, max_length=200_000)
    visibility: Literal["public", "internal", "admin"] = "internal"


class TicketDraftRequest(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=5, max_length=4000)
    priority: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"


class TicketDraftResponse(BaseModel):
    draft_id: str
    status: str
    message: str


class TicketResponse(BaseModel):
    ticket_id: str
    draft_id: str
    title: str
    status: str
    idempotent: bool = False


class EvaluationResponse(BaseModel):
    suite: str
    total: int
    hits: int
    pass_rate: float
    cases: list[dict]


class AuditLogResponse(BaseModel):
    id: int
    username: str
    action: str
    resource: str
    outcome: str
    details: dict | str
    created_at: str

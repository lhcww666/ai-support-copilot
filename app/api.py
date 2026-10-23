from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.agent import SupportAgent
from app.config import Settings
from app.documents import DocumentError, extract_document_text
from app.evaluation import EvaluationService
from app.knowledge import KnowledgeService
from app.repositories import SqliteRepository
from app.schemas import (
    AuditLogResponse,
    ChatRequest,
    ChatResponse,
    DocumentResponse,
    DocumentTextRequest,
    EvaluationResponse,
    LoginRequest,
    TicketDraftRequest,
    TicketDraftResponse,
    TicketResponse,
    TokenResponse,
    UserResponse,
)
from app.security import AuthError, AuthService, User
from app.tickets import TicketService

router = APIRouter(prefix="/api/v1")
bearer = HTTPBearer(auto_error=False)


def _service(request: Request, name: str):
    return getattr(request.app.state, name)


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    try:
        return _service(request, "auth").decode(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def _settings(request: Request) -> Settings:
    return _service(request, "settings")


def _require(user: User, minimum: str) -> None:
    if {"viewer": 1, "operator": 2, "admin": 3}[user.role] < {
        "viewer": 1,
        "operator": 2,
        "admin": 3,
    }[minimum]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"需要 {minimum} 权限")


@router.post("/auth/login", response_model=TokenResponse)
def login(request: Request, body: LoginRequest) -> TokenResponse:
    auth: AuthService = _service(request, "auth")
    try:
        token = auth.login(body.username, body.password)
        user = auth.decode(token)
        return TokenResponse(
            access_token=token,
            user=UserResponse(
                username=user.username,
                display_name=user.display_name,
                role=user.role,
            ),
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/auth/me", response_model=UserResponse)
def me(user: Annotated[User, Depends(current_user)]) -> UserResponse:
    return UserResponse(username=user.username, display_name=user.display_name, role=user.role)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    body: ChatRequest,
    user: Annotated[User, Depends(current_user)],
) -> ChatResponse:
    agent: SupportAgent = _service(request, "agent")
    try:
        result = await agent.chat(user, body.query, body.conversation_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return ChatResponse(
        conversation_id=result.conversation_id,
        answer=result.answer,
        sources=[
            {
                "document_id": source.document_id,
                "title": source.title,
                "visibility": source.visibility,
                "score": source.score,
                "snippet": source.content[:220],
            }
            for source in result.sources
        ],
        tool_calls=result.tool_calls,
        planner=result.planner,
        fallback=result.fallback,
    )


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    body: ChatRequest,
    user: Annotated[User, Depends(current_user)],
) -> StreamingResponse:
    agent: SupportAgent = _service(request, "agent")

    async def events() -> AsyncIterator[str]:
        try:
            async for event in agent.stream(user, body.query, body.conversation_id):
                data = json.dumps(event["data"], ensure_ascii=False)
                yield f"event: {event['event']}\ndata: {data}\n\n"
        except Exception as exc:
            data = json.dumps({"message": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {data}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/documents", response_model=list[DocumentResponse])
def documents(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[DocumentResponse]:
    knowledge: KnowledgeService = _service(request, "knowledge")
    return [
        DocumentResponse(
            id=item["id"],
            title=item["title"],
            visibility=item["visibility"],
            created_by=item["created_by"],
            created_at=item["created_at"],
            size=len(item["content"]),
        )
        for item in knowledge.list_documents(user.role)
    ]


@router.post("/documents/upload", response_model=DocumentResponse)
async def upload_document(
    request: Request,
    user: Annotated[User, Depends(current_user)],
    file: Annotated[UploadFile, File()],
    visibility: str = "internal",
) -> DocumentResponse:
    _require(user, "admin")
    if visibility not in {"public", "internal", "admin"}:
        raise HTTPException(status_code=400, detail="可见范围无效")
    settings = _settings(request)
    payload = await file.read(settings.max_upload_bytes + 1)
    try:
        content = extract_document_text(
            file.filename or "upload.txt",
            payload,
            settings.max_upload_bytes,
        )
    except DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    title = Path(file.filename or "document").stem
    knowledge: KnowledgeService = _service(request, "knowledge")
    document_id = knowledge.add_document(title, content, visibility, user.username)
    _service(request, "repository").audit(
        user.username, "DOCUMENT_UPLOAD", document_id, "success", {"title": title}
    )
    document = next(item for item in knowledge.list_documents("admin") if item["id"] == document_id)
    return DocumentResponse(
        id=document["id"],
        title=document["title"],
        visibility=document["visibility"],
        created_by=document["created_by"],
        created_at=document["created_at"],
        size=len(document["content"]),
    )


@router.post("/documents/text", response_model=DocumentResponse)
def add_text_document(
    request: Request,
    body: DocumentTextRequest,
    user: Annotated[User, Depends(current_user)],
) -> DocumentResponse:
    _require(user, "admin")
    knowledge: KnowledgeService = _service(request, "knowledge")
    document_id = knowledge.add_document(
        body.title, body.content, body.visibility, user.username
    )
    _service(request, "repository").audit(
        user.username,
        "DOCUMENT_CREATE",
        document_id,
        "success",
        {"title": body.title},
    )
    document = next(item for item in knowledge.list_documents("admin") if item["id"] == document_id)
    return DocumentResponse(
        id=document["id"],
        title=document["title"],
        visibility=document["visibility"],
        created_by=document["created_by"],
        created_at=document["created_at"],
        size=len(document["content"]),
    )


@router.delete("/documents/{document_id}")
def delete_document(
    request: Request,
    document_id: str,
    user: Annotated[User, Depends(current_user)],
) -> dict:
    _require(user, "admin")
    knowledge: KnowledgeService = _service(request, "knowledge")
    deleted = knowledge.delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="文档不存在")
    _service(request, "repository").audit(
        user.username, "DOCUMENT_DELETE", document_id, "success", {}
    )
    return {"deleted": True, "document_id": document_id}


@router.get("/orders/{order_id}")
def order_status(
    request: Request,
    order_id: str,
    user: Annotated[User, Depends(current_user)],
) -> dict:
    try:
        result = _service(request, "orders").get_status(user, order_id)
        _service(request, "repository").audit(
            user.username,
            "ORDER_QUERY",
            order_id.upper(),
            "success",
            {"status": result["status"]},
        )
        return result
    except AuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tickets/drafts", response_model=TicketDraftResponse)
def create_ticket_draft(
    request: Request,
    body: TicketDraftRequest,
    user: Annotated[User, Depends(current_user)],
) -> TicketDraftResponse:
    service: TicketService = _service(request, "tickets")
    try:
        draft_id = service.prepare(user, body.title, body.description, body.priority)
    except AuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return TicketDraftResponse(
        draft_id=draft_id,
        status="DRAFT",
        message="工单草稿已生成，需要用户确认",
    )


@router.post("/tickets/{draft_id}/confirm", response_model=TicketResponse)
def confirm_ticket(
    request: Request,
    draft_id: str,
    user: Annotated[User, Depends(current_user)],
) -> TicketResponse:
    service: TicketService = _service(request, "tickets")
    try:
        ticket, idempotent = service.confirm(user, draft_id)
    except AuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TicketResponse(
        ticket_id=ticket["ticket_id"],
        draft_id=ticket["draft_id"],
        title=ticket["title"],
        status=ticket["status"],
        idempotent=idempotent,
    )


@router.get("/evaluations/rag", response_model=EvaluationResponse)
def rag_evaluation(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> EvaluationResponse:
    _require(user, "admin")
    service: EvaluationService = _service(request, "evaluation")
    return EvaluationResponse(**service.run_rag_evaluation())


@router.get("/admin/audit-logs", response_model=list[AuditLogResponse])
def audit_logs(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[AuditLogResponse]:
    _require(user, "admin")
    repository: SqliteRepository = _service(request, "repository")
    return [AuditLogResponse(**item) for item in repository.list_audit_logs()]


@router.get("/runtime")
def runtime(request: Request, user: Annotated[User, Depends(current_user)]) -> dict:
    settings = _settings(request)
    knowledge: KnowledgeService = _service(request, "knowledge")
    repository: SqliteRepository = _service(request, "repository")
    return {
        "app_env": settings.app_env,
        "llm_mode": "langchain-agent" if settings.llm_enabled else "offline-rule",
        "embedding_mode": "openai" if settings.embedding_api_key else "hash",
        "documents": repository.document_count(),
        "retrieval_visible": len(knowledge.list_documents(user.role)),
        "user": user.username,
        "role": user.role,
    }

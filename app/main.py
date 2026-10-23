from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent import SupportAgent
from app.api import router
from app.config import Settings
from app.evaluation import EvaluationService
from app.knowledge import KnowledgeService
from app.orders import OrderService
from app.repositories import SqliteRepository
from app.security import AuthService
from app.seed import seed_documents
from app.tickets import TicketService


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()
    repository = SqliteRepository(resolved.database_path)
    knowledge = KnowledgeService(repository, resolved)
    tickets = TicketService(repository)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.initialize()
        seed_documents(repository, resolved.seed_dir)
        knowledge.refresh()
        yield

    application = FastAPI(
        title=resolved.app_name,
        version="0.1.0",
        description="Role-aware RAG support copilot with LangChain tools and evaluations.",
        lifespan=lifespan,
    )
    application.state.settings = resolved
    application.state.repository = repository
    application.state.auth = AuthService(resolved)
    application.state.orders = OrderService()
    application.state.tickets = tickets
    application.state.knowledge = knowledge
    application.state.agent = SupportAgent(
        resolved, repository, knowledge, application.state.orders, tickets
    )
    application.state.evaluation = EvaluationService(knowledge)

    static_dir = Path(__file__).resolve().parent / "static"
    application.mount("/static", StaticFiles(directory=static_dir), name="static")
    application.include_router(router)

    @application.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "llm_mode": "langchain-agent" if resolved.llm_enabled else "offline-rule",
            "documents": repository.document_count(),
        }

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    return application


app = create_app()

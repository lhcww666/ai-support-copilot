from __future__ import annotations

import asyncio
import re
import threading
from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import Settings
from app.embeddings import HashEmbeddings, text_tokens
from app.pgvector_store import PgVectorStore
from app.repositories import SqliteRepository
from app.tei_embeddings import TeiEmbeddings

VISIBILITY_LEVEL = {"public": 1, "internal": 2, "admin": 3}
ROLE_LEVEL = {"viewer": 1, "operator": 2, "admin": 3}


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    document_id: str
    title: str
    visibility: str
    content: str
    score: float


def build_embeddings(settings: Settings) -> Embeddings:
    provider = settings.embedding_provider
    if provider == "tei":
        return TeiEmbeddings(
            base_url=settings.embedding_base_url,
            dimensions=settings.embedding_dimensions,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    if provider == "openai" and settings.embedding_api_key.strip():
        return OpenAIEmbeddings(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            timeout=settings.llm_timeout_seconds,
            dimensions=settings.embedding_dimensions,
        )
    if provider == "hash":
        return HashEmbeddings(dimensions=settings.embedding_dimensions)
    raise ValueError(f"不支持的 Embedding 供应商: {provider}")


class KnowledgeService:
    def __init__(
        self,
        repository: SqliteRepository,
        settings: Settings,
        embeddings: Embeddings | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.embeddings = embeddings or build_embeddings(settings)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=420,
            chunk_overlap=70,
            separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
        )
        self._memory_store = InMemoryVectorStore(embedding=self.embeddings)
        self._pg_store: PgVectorStore | None = None
        if settings.vector_store == "pgvector":
            self._pg_store = PgVectorStore(
                dsn=settings.pgvector_dsn,
                embeddings=self.embeddings,
                dimensions=settings.embedding_dimensions,
            )
        elif settings.vector_store != "memory":
            raise ValueError(f"不支持的向量存储: {settings.vector_store}")
        self._lock = threading.RLock()

    def initialize(self) -> None:
        if self._pg_store:
            self._pg_store.ensure_schema()
            if self._pg_store.count() == 0:
                self.refresh()
        else:
            self.refresh()

    def refresh(self) -> None:
        with self._lock:
            documents = self._all_documents()
            if self._pg_store:
                self._pg_store.clear()
                self._pg_store.add_documents(documents)
            else:
                self._memory_store = InMemoryVectorStore.from_documents(
                    documents=documents,
                    embedding=self.embeddings,
                )

    def add_document(
        self,
        title: str,
        content: str,
        visibility: str,
        created_by: str,
    ) -> str:
        document_id = self.repository.insert_document(
            title=title,
            content=content,
            visibility=visibility,
            created_by=created_by,
        )
        try:
            if self._pg_store:
                self._pg_store.add_documents(
                    self._split_document(
                        {
                            "id": document_id,
                            "title": title,
                            "content": content,
                            "visibility": visibility,
                        }
                    )
                )
            else:
                self.refresh()
        except Exception:
            self.repository.delete_document(document_id)
            raise
        return document_id

    def delete_document(self, document_id: str) -> bool:
        if self._pg_store:
            self._pg_store.delete_document(document_id)
            deleted = self.repository.delete_document(document_id)
        else:
            deleted = self.repository.delete_document(document_id)
        if deleted and not self._pg_store:
            self.refresh()
        return deleted

    def list_documents(self, role: str) -> list[dict[str, Any]]:
        return self.repository.list_documents(_visible_levels(role))

    def search(self, query: str, role: str, limit: int | None = None) -> list[RetrievedChunk]:
        if not query.strip():
            return []
        limit = limit or self.settings.retrieval_limit
        query_tokens = text_tokens(query)
        with self._lock:
            if self._pg_store:
                matches = self._pg_store.similarity_search_with_score(
                    query,
                    k=max(limit * 8, 24),
                    visibilities=_visible_levels(role),
                )
            else:
                matches = self._memory_store.similarity_search_with_score(
                    query,
                    k=max(limit * 8, 24),
                    filter=lambda doc: _role_can_read(
                        role, str(doc.metadata.get("visibility", "admin"))
                    ),
                )

        ranked: list[RetrievedChunk] = []
        for document, vector_score in matches:
            chunk_tokens = text_tokens(document.page_content)
            overlap = len(query_tokens & chunk_tokens) / max(1, len(query_tokens))
            title_overlap = len(query_tokens & text_tokens(str(document.metadata["title"]))) / max(
                1, len(query_tokens)
            )
            combined = 0.62 * max(float(vector_score), 0.0) + 0.28 * overlap + 0.1 * title_overlap
            ranked.append(
                RetrievedChunk(
                    document_id=str(document.metadata["document_id"]),
                    title=str(document.metadata["title"]),
                    visibility=str(document.metadata["visibility"]),
                    content=re.sub(r"\s+", " ", document.page_content).strip(),
                    score=round(combined, 4),
                )
            )

        ordered = sorted(ranked, key=lambda value: value.score, reverse=True)
        if not ordered:
            return []
        minimum_score = max(0.06, ordered[0].score * 0.35)
        best_by_document: dict[str, RetrievedChunk] = {}
        for item in ordered:
            if item.score < minimum_score:
                break
            if item.document_id not in best_by_document:
                best_by_document[item.document_id] = item
            if len(best_by_document) >= limit:
                break
        return list(best_by_document.values())

    async def asearch(
        self,
        query: str,
        role: str,
        limit: int | None = None,
    ) -> list[RetrievedChunk]:
        return await asyncio.to_thread(self.search, query, role, limit)

    def _all_documents(self) -> list[Document]:
        documents: list[Document] = []
        for item in self.repository.list_documents(set(VISIBILITY_LEVEL)):
            documents.extend(self._split_document(item))
        return documents

    def _split_document(self, item: dict[str, Any]) -> list[Document]:
        return [
            Document(
                page_content=chunk,
                metadata={
                    "document_id": item["id"],
                    "title": item["title"],
                    "visibility": item["visibility"],
                    "chunk_index": index,
                },
            )
            for index, chunk in enumerate(self.splitter.split_text(item["content"]))
        ]


def _visible_levels(role: str) -> set[str]:
    level = ROLE_LEVEL.get(role, 0)
    return {name for name, required in VISIBILITY_LEVEL.items() if level >= required}


def _role_can_read(role: str, visibility: str) -> bool:
    return ROLE_LEVEL.get(role, 0) >= VISIBILITY_LEVEL.get(visibility, 99)

from __future__ import annotations

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
from app.repositories import SqliteRepository

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
    if settings.embedding_api_key.strip():
        return OpenAIEmbeddings(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            timeout=settings.llm_timeout_seconds,
        )
    return HashEmbeddings()


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
        self._vectorstore = InMemoryVectorStore(embedding=self.embeddings)
        self._lock = threading.RLock()

    def refresh(self) -> None:
        with self._lock:
            documents: list[Document] = []
            for item in self.repository.list_documents(set(VISIBILITY_LEVEL)):
                for index, chunk in enumerate(self.splitter.split_text(item["content"])):
                    documents.append(
                        Document(
                            page_content=chunk,
                            metadata={
                                "document_id": item["id"],
                                "title": item["title"],
                                "visibility": item["visibility"],
                                "chunk_index": index,
                            },
                        )
                    )
            self._vectorstore = InMemoryVectorStore.from_documents(
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
        self.refresh()
        return document_id

    def delete_document(self, document_id: str) -> bool:
        deleted = self.repository.delete_document(document_id)
        if deleted:
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
            matches = self._vectorstore.similarity_search_with_score(
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


def _visible_levels(role: str) -> set[str]:
    level = ROLE_LEVEL.get(role, 0)
    return {name for name, required in VISIBILITY_LEVEL.items() if level >= required}


def _role_can_read(role: str, visibility: str) -> bool:
    return ROLE_LEVEL.get(role, 0) >= VISIBILITY_LEVEL.get(visibility, 99)

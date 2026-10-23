from __future__ import annotations

import re

import psycopg
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row


class PgVectorStore:
    def __init__(
        self,
        dsn: str,
        embeddings: Embeddings,
        dimensions: int,
        table_name: str = "support_chunks",
    ) -> None:
        if not dsn:
            raise ValueError("PGVECTOR_DSN 不能为空")
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", table_name):
            raise ValueError("非法向量表名")
        self.dsn = dsn
        self.embeddings = embeddings
        self.dimensions = dimensions
        self.table_name = table_name

    def ensure_schema(self) -> None:
        index_name = f"{self.table_name}_embedding_idx"
        with self._connect() as connection:
            connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector({self.dimensions}) NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                CREATE INDEX IF NOT EXISTS {index_name}
                ON {self.table_name}
                USING hnsw (embedding vector_cosine_ops)
                """
            )

    def add_documents(self, documents: list[Document]) -> None:
        if not documents:
            return
        vectors = self.embeddings.embed_documents(
            [document.page_content for document in documents]
        )
        values = []
        for document, vector in zip(documents, vectors, strict=True):
            metadata = document.metadata
            document_id = str(metadata["document_id"])
            chunk_index = int(metadata["chunk_index"])
            values.append(
                (
                    f"{document_id}:{chunk_index}",
                    document_id,
                    str(metadata["title"]),
                    str(metadata["visibility"]),
                    chunk_index,
                    document.page_content,
                    Vector(vector),
                )
            )
        with self._connect() as connection:
            connection.executemany(
                f"""
                INSERT INTO {self.table_name}
                    (id, document_id, title, visibility, chunk_index, content, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    visibility = EXCLUDED.visibility,
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding
                """,
                values,
            )

    def similarity_search_with_score(
        self,
        query: str,
        k: int,
        visibilities: set[str],
    ) -> list[tuple[Document, float]]:
        if not visibilities:
            return []
        query_vector = Vector(self.embeddings.embed_query(query))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT document_id, title, visibility, chunk_index, content,
                       1 - (embedding <=> %s::vector) AS score
                FROM {self.table_name}
                WHERE visibility = ANY(%s)
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_vector, sorted(visibilities), query_vector, k),
            ).fetchall()
        return [
            (
                Document(
                    page_content=row["content"],
                    metadata={
                        "document_id": row["document_id"],
                        "title": row["title"],
                        "visibility": row["visibility"],
                        "chunk_index": row["chunk_index"],
                    },
                ),
                float(row["score"]),
            )
            for row in rows
        ]

    def delete_document(self, document_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                f"DELETE FROM {self.table_name} WHERE document_id = %s",
                (document_id,),
            )

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS count FROM {self.table_name}"
            ).fetchone()
        return int(row["count"])

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute(f"TRUNCATE TABLE {self.table_name}")

    def drop_table(self) -> None:
        with self._connect() as connection:
            connection.execute(f"DROP TABLE IF EXISTS {self.table_name}")

    def _connect(self):
        connection = psycopg.connect(
            self.dsn,
            row_factory=dict_row,
            autocommit=True,
            connect_timeout=5,
        )
        register_vector(connection)
        return connection

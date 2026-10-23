from __future__ import annotations

import os
import uuid

import pytest
from langchain_core.documents import Document

from app.embeddings import HashEmbeddings
from app.pgvector_store import PgVectorStore


@pytest.mark.skipif(
    not os.getenv("PGVECTOR_TEST_DSN"),
    reason="PGVECTOR_TEST_DSN is not configured",
)
def test_pgvector_store_roundtrip_and_visibility_filter():
    table_name = f"test_chunks_{uuid.uuid4().hex[:10]}"
    store = PgVectorStore(
        dsn=os.environ["PGVECTOR_TEST_DSN"],
        embeddings=HashEmbeddings(dimensions=32),
        dimensions=32,
        table_name=table_name,
    )
    store.ensure_schema()
    try:
        store.add_documents(
            [
                Document(
                    page_content="退款超过一千元需要客服主管审批。",
                    metadata={
                        "document_id": "doc-public",
                        "title": "公开退款规则",
                        "visibility": "public",
                        "chunk_index": 0,
                    },
                ),
                Document(
                    page_content="管理员事故响应手册包含密钥轮换步骤。",
                    metadata={
                        "document_id": "doc-admin",
                        "title": "管理员手册",
                        "visibility": "admin",
                        "chunk_index": 0,
                    },
                ),
            ]
        )

        public_results = store.similarity_search_with_score(
            "退款主管审批",
            k=2,
            visibilities={"public"},
        )
        admin_results = store.similarity_search_with_score(
            "密钥轮换",
            k=2,
            visibilities={"public", "internal", "admin"},
        )

        assert public_results[0][0].metadata["visibility"] == "public"
        assert all(
            document.metadata["visibility"] == "public"
            for document, _score in public_results
        )
        assert any(
            document.metadata["document_id"] == "doc-admin"
            for document, _score in admin_results
        )
        assert store.count() == 2
    finally:
        store.drop_table()

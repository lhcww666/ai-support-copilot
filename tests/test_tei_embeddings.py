from __future__ import annotations

import json

import httpx
import pytest

from app.tei_embeddings import TeiEmbeddings


def test_tei_embeddings_parse_batch_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/embed"
        payload = json.loads(request.content)
        assert payload["inputs"] == ["第一段", "第二段"]
        return httpx.Response(200, json=[[0.1, 0.2, 0.3], [0.3, 0.2, 0.1]])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    embeddings = TeiEmbeddings(
        "http://embedding:80",
        dimensions=3,
        client=client,
    )

    vectors = embeddings.embed_documents(["第一段", "第二段"])

    assert vectors == [[0.1, 0.2, 0.3], [0.3, 0.2, 0.1]]


def test_tei_embeddings_reject_wrong_dimensions():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json=[[0.1, 0.2]])
        )
    )
    embeddings = TeiEmbeddings(
        "http://embedding:80",
        dimensions=3,
        client=client,
    )

    with pytest.raises(RuntimeError, match="维度异常"):
        embeddings.embed_query("测试")

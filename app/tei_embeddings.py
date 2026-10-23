from __future__ import annotations

from typing import Any

import httpx
from langchain_core.embeddings import Embeddings


class TeiEmbeddings(Embeddings):
    """LangChain adapter for Hugging Face Text Embeddings Inference."""

    def __init__(
        self,
        base_url: str,
        dimensions: int,
        timeout_seconds: float = 30,
        batch_size: int = 16,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.dimensions = dimensions
        self.batch_size = batch_size
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=timeout_seconds)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            vectors.extend(self._request(batch))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self._request([text])
        return vectors[0]

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _request(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self.client.post(
                f"{self.base_url}/embed",
                json={"inputs": texts, "truncate": True},
            )
            response.raise_for_status()
            payload: Any = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"TEI Embedding 请求失败: {exc}") from exc

        if not isinstance(payload, list) or len(payload) != len(texts):
            raise RuntimeError("TEI Embedding 返回数量与输入不一致")
        vectors: list[list[float]] = []
        for vector in payload:
            if not isinstance(vector, list) or len(vector) != self.dimensions:
                raise RuntimeError(
                    f"TEI Embedding 维度异常，期望 {self.dimensions}，实际 "
                    f"{len(vector) if isinstance(vector, list) else 'unknown'}"
                )
            vectors.append([float(value) for value in vector])
        return vectors

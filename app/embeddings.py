from __future__ import annotations

import hashlib
import math
import re

from langchain_core.embeddings import Embeddings


class HashEmbeddings(Embeddings):
    """Deterministic offline embedding based on token hashing and Chinese bigrams."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = _tokens(text)
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            return [value / norm for value in vector]
        return vector


def text_tokens(text: str) -> set[str]:
    return set(_tokens(text))


def _tokens(text: str) -> list[str]:
    normalized = text.lower()
    latin = re.findall(r"[a-z0-9_]+", normalized)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
    chinese: list[str] = []
    for run in chinese_runs:
        chinese.extend(run)
        chinese.extend(run[index : index + 2] for index in range(max(0, len(run) - 1)))
    return latin + chinese

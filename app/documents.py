from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}


class DocumentError(ValueError):
    pass


def extract_document_text(filename: str, payload: bytes, max_bytes: int) -> str:
    if len(payload) > max_bytes:
        raise DocumentError(f"文件不能超过 {max_bytes // 1024} KB")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise DocumentError("只支持 txt、md 和 pdf 文件")

    if suffix == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(payload))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise DocumentError("PDF 解析失败") from exc
    else:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentError("文本文件必须使用 UTF-8 编码") from exc

    cleaned = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if len(cleaned) < 10:
        raise DocumentError("文档没有可提取的有效文本")
    if len(cleaned) > 500_000:
        raise DocumentError("文档文本过长，请拆分后上传")
    return cleaned

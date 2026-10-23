from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import Settings


@dataclass(frozen=True, slots=True)
class RewriteResult:
    original_query: str
    query: str
    rewritten: bool


class QueryRewriteService:
    def __init__(
        self,
        settings: Settings,
        model_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.settings = settings
        self.model_factory = model_factory

    async def rewrite(self, query: str, history: list[dict[str, str]]) -> RewriteResult:
        if (
            not self.settings.llm_enabled
            or not self.settings.query_rewrite_enabled
            or not history
        ):
            return RewriteResult(query, query, False)
        model = self.model_factory() if self.model_factory else ChatOpenAI(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            model=self.settings.llm_model,
            temperature=0.0,
            timeout=self.settings.llm_timeout_seconds,
            max_retries=1,
            model_kwargs={"max_tokens": self.settings.query_rewrite_max_tokens},
            use_responses_api=False,
        )
        history_text = "\n".join(
            f"{'用户' if item['role'] == 'user' else '客服'}: {item['content']}"
            for item in history
        )
        try:
            response = await model.ainvoke(
                [
                    SystemMessage(
                        content=(
                            "你是检索查询改写器。结合历史把当前追问改写成一个完整、独立的中文"
                            "检索问题。保留订单号、金额、业务名词和限制条件。不要回答问题，"
                            "不要添加历史中不存在的事实，只输出一行改写结果。"
                        )
                    ),
                    HumanMessage(
                        content=f"历史：\n{history_text}\n\n当前问题：{query}"
                    ),
                ]
            )
            candidate = _normalize(_message_text(response))
            if not candidate:
                return RewriteResult(query, query, False)
            return RewriteResult(query, candidate, candidate != query)
        except Exception:
            return RewriteResult(query, query, False)


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") in {"text", "output_text"}
        )
    return str(content)


def _normalize(candidate: str) -> str:
    text = candidate.strip().splitlines()[0].strip()
    for prefix in ("改写后：", "改写结果：", "检索问题："):
        text = text.removeprefix(prefix)
    text = text.strip().strip('"“”')
    if not text or len(text) > 300:
        return ""
    return text

from __future__ import annotations

from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage

from app.query_rewrite import QueryRewriteService


class FakeRewriteModel:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1
        return AIMessage(content=self.content)


@pytest.mark.asyncio
async def test_rewrites_follow_up_with_conversation_history(settings):
    rewrite_settings = replace(settings, llm_api_key="fake-key")
    model = FakeRewriteModel("“退款超过 1000 元的定制商品如何处理？”")
    service = QueryRewriteService(rewrite_settings, model_factory=lambda: model)
    history = [
        {"role": "user", "content": "退款超过 1000 元怎么处理？"},
        {"role": "assistant", "content": "需要客服主管审批。"},
    ]

    result = await service.rewrite("那定制商品呢？", history)

    assert result.original_query == "那定制商品呢？"
    assert result.query == "退款超过 1000 元的定制商品如何处理？"
    assert result.rewritten is True
    assert model.calls == 1


@pytest.mark.asyncio
async def test_does_not_rewrite_first_turn(settings):
    rewrite_settings = replace(settings, llm_api_key="fake-key")
    service = QueryRewriteService(
        rewrite_settings,
        model_factory=lambda: FakeRewriteModel("不应调用"),
    )

    result = await service.rewrite("退款超过 1000 元怎么处理？", [])

    assert result.query == result.original_query
    assert result.rewritten is False


@pytest.mark.asyncio
async def test_rewrite_can_be_disabled(settings):
    rewrite_settings = replace(
        settings,
        llm_api_key="fake-key",
        query_rewrite_enabled=False,
    )
    service = QueryRewriteService(
        rewrite_settings,
        model_factory=lambda: FakeRewriteModel("不应调用"),
    )
    history = [{"role": "user", "content": "上一轮问题"}]

    result = await service.rewrite("那这个呢？", history)

    assert result.query == "那这个呢？"
    assert result.rewritten is False

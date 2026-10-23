from __future__ import annotations

from dataclasses import replace

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app.agent import PreparedChat, SupportAgent
from app.knowledge import KnowledgeService
from app.orders import OrderService
from app.repositories import SqliteRepository
from app.security import User
from app.seed import seed_documents
from app.tickets import TicketService
from app.tools import build_tools, tool_context


class ToolCallingFakeChatModel(GenericFakeChatModel):
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


@pytest.mark.asyncio
async def test_agent_streams_langchain_output_without_duplicate_text(settings):
    llm_settings = replace(settings, llm_api_key="fake-key")
    repository = SqliteRepository(llm_settings.database_path)
    repository.initialize()
    seed_documents(repository, llm_settings.seed_dir)
    knowledge = KnowledgeService(repository, llm_settings)
    knowledge.refresh()
    service = SupportAgent(
        llm_settings,
        repository,
        knowledge,
        OrderService(),
        TicketService(repository),
        model_factory=lambda: ToolCallingFakeChatModel(
            messages=iter([AIMessage(content="流式回答测试")])
        ),
    )
    user = User("viewer", "只读用户", "viewer")

    events = [event async for event in service.stream(user, "标准订单多久发货？")]

    assert events[0]["event"] == "meta"
    assert events[0]["data"]["planner"] == "langchain-agent"
    streamed_text = "".join(
        event["data"]["text"] for event in events if event["event"] == "token"
    )
    assert streamed_text == "流式回答测试"
    assert events[-1]["event"] == "done"
    conversation_id = events[0]["data"]["conversation_id"]
    messages = repository.messages(conversation_id, user.username, 10)
    assert messages[-1] == {"role": "assistant", "content": "流式回答测试"}


@pytest.mark.asyncio
async def test_agent_streams_tool_start_and_result_events(settings):
    repository = SqliteRepository(settings.database_path)
    repository.initialize()
    knowledge = KnowledgeService(repository, settings)
    service = SupportAgent(
        settings,
        repository,
        knowledge,
        OrderService(),
        TicketService(repository),
    )
    user = User("operator", "客服专员", "operator")
    prepared = PreparedChat(
        "conv-test",
        [],
        [],
        "查询订单 SO-1001",
        "查询订单 SO-1001",
        False,
    )

    class FakeEventAgent:
        async def astream_events(self, _input, *, version):
            assert version == "v2"
            yield {
                "event": "on_tool_start",
                "name": "query_order_status",
                "data": {"input": {"order_id": "SO-1001"}},
            }
            service.tools[0].invoke({"order_id": "SO-1001"})
            yield {
                "event": "on_tool_end",
                "name": "query_order_status",
                "data": {"output": "tool-complete"},
            }
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": AIMessage(content="订单状态为运输中")},
            }
            yield {
                "event": "on_chat_model_end",
                "data": {"output": AIMessage(content="订单状态为运输中")},
            }

    service._build_agent = lambda _user, _sources: FakeEventAgent()
    events = [
        event
        async for event in service._stream_langchain(
            user,
            "查询订单 SO-1001",
            prepared,
        )
    ]
    event_types = [event["event"] for event in events]
    tool_start = next(event for event in events if event["event"] == "tool-start")
    tool_result = next(event for event in events if event["event"] == "tool")

    assert event_types.index("tool-start") < event_types.index("tool")
    assert tool_start["data"]["name"] == "query_order_status"
    assert tool_start["data"]["input"]["order_id"] == "SO-1001"
    assert tool_result["data"]["output"]["status"] == "运输中"
    assert event_types.count("tool") == 1
    assert event_types.count("token") == 1


@pytest.mark.asyncio
async def test_langchain_agent_executes_project_tool_loop(settings):
    repository = SqliteRepository(settings.database_path)
    repository.initialize()
    tools = build_tools(OrderService(), TicketService(repository))
    model = ToolCallingFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "query_order_status",
                            "args": {"order_id": "SO-1001"},
                            "id": "call-order-1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="订单查询工具已执行"),
            ]
        )
    )
    agent = create_agent(model=model, tools=tools, system_prompt="只处理客服任务")
    user = User("operator", "客服专员", "operator")

    with tool_context(user) as calls:
        result = await agent.ainvoke({"messages": [HumanMessage(content="查询订单 SO-1001")]})

    assert calls[0]["name"] == "query_order_status"
    assert calls[0]["output"]["status"] == "运输中"
    assert result["messages"][-1].content == "订单查询工具已执行"

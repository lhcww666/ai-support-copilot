# Architecture

## 分层

```text
app/
  api.py             HTTP / SSE / 权限依赖
  agent.py           LangChain Agent、离线降级、会话编排
  knowledge.py       切分、Embedding、向量检索、混合重排
  tools.py           LangChain Tool 与用户上下文
  orders.py          订单业务
  tickets.py         工单草稿与确认
  repositories.py    SQLite 持久化
  security.py        Token、角色和可见范围
  evaluation.py      固定检索评测
  static/            Web 控制台
```

`app.main.create_app()` 负责依赖组装，测试可以为每次请求创建独立 SQLite 数据库。

## RAG

```text
文档
  -> RecursiveCharacterTextSplitter
  -> HashEmbeddings 或 OpenAIEmbeddings
  -> InMemoryVectorStore
  -> 按角色过滤
  -> 向量分数 + 关键词重叠重排
  -> Top 4 引用
```

检索前使用用户角色过滤文档，不能依赖前端隐藏。文档升级为真实向量库时应保留相同的
`document_id`、`visibility` 和候选后过滤逻辑。

多轮对话中，系统先使用 DeepSeek 把追问改写为独立检索问题：

```text
上一轮对话 + 当前追问
  -> QueryRewriteService
  -> 独立检索问题
  -> 向量与关键词混合检索
```

改写失败、关闭改写或第一轮对话时，直接使用原问题。

## LangChain Agent

配置模型 Key 后：

```text
用户问题 + 最近会话 + 已检索引用
  -> create_agent
  -> 模型选择工具
  -> query_order_status / prepare_support_ticket
  -> on_tool_start 推送 tool-start
  -> on_tool_end 推送工具结果
  -> astream_events 推送 on_chat_model_stream Token
  -> 模型生成最终回答
```

没有模型 Key 或模型调用失败时切换到确定性规则：

```text
订单号正则 -> 订单工具
工单意图 -> 工单草稿工具
其他问题 -> 引用片段回答
```

工具使用 `ContextVar` 恢复当前用户，不让模型直接传递用户身份或 Token。

模型层支持 OpenAI-Compatible 供应商配置。`LLM_PROVIDER=deepseek` 时默认使用
`https://api.deepseek.com/v1` 和 `deepseek-chat`；Embedding 供应商单独配置。

## 写操作安全

```text
prepare_support_ticket
  -> ticket_drafts
  -> 用户显式确认
  -> tickets
  -> 重复确认返回已有 ticket_id
```

模型不能直接创建正式工单。`ticket_drafts.requester` 和 `tickets.draft_id` 唯一约束提供
所有权与幂等保障。

## 评测

10 条固定问题检查期望文档是否进入 Top 4。评测只调用检索服务，不创建会话、工单或业务数据，
因此不会污染数据库。

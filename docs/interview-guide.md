# 简历与面试说明

## 项目定位

> 基于 FastAPI 与 LangChain 构建角色感知的企业客服 Copilot，完成文档切分、混合检索、
> 引用来源、工具调用、会话持久化、人工确认和固定评测。

## 技术栈

- Python 3.13、FastAPI、Pydantic、SSE
- LangChain 1.x、LangChain Core、LangChain OpenAI
- RecursiveCharacterTextSplitter、Embeddings、InMemoryVectorStore
- Tool Calling、`create_agent`、DeepSeek/OpenAI-Compatible 适配、离线规则降级
- SQLite、Docker、GitHub Actions、Pytest、Ruff

## 可写进简历的要点

- 基于 FastAPI 设计知识库客服 API，通过 HMAC Token 和角色过滤实现 PUBLIC/INTERNAL/ADMIN
  三级文档权限，避免前端隐藏造成的越权检索。
- 使用 LangChain 完成文档切分、Embedding、向量检索和关键词混合重排，返回可追溯引用并构建
  10 条固定评测集。
- 使用 LangChain Tool Calling 接入订单查询与工单草稿，模型只负责选择工具，正式写操作必须经过
  用户确认和数据库唯一约束保证幂等。
- 设计离线规则降级，在未配置模型或供应商失败时仍能完成知识检索、订单查询和工单草稿流程。
- 使用 SQLite 保存会话、消息、工单和审计日志，补齐角色校验、会话隔离、SSE 输出、Docker 和 CI。

## 高频问题

**为什么不完全依赖 LangChain Agent？**

Agent 适合不确定的工具选择，但权限、数据库写入和幂等必须由确定性代码控制。模型失败时也需要
可预测的降级路径。

**为什么用单 Agent？**

当前只有知识检索、订单查询和工单三个边界，单 Agent 加清晰工具已经足够。多 Agent 会增加路由
成本和错误面，不能自动代表效果更好。

**如何防止 RAG 越权？**

检索时传入可见范围过滤函数，而不是检索后再交给前端隐藏。文档元数据和查询角色在服务端校验。

**如何防止模型重复建工单？**

模型只能创建草稿；用户显式确认后写正式工单，`draft_id` 唯一约束和重复查询保证幂等。

**离线哈希 Embedding 是否算 RAG？**

它用于无网络演示和确定性测试，完整链路是真实的，但语义能力弱。生产应替换为真实 Embedding，
并补充 pgvector/Qdrant、Rerank 和检索指标。

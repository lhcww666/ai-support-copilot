# Verification

## 开发环境

- Python 3.13.9
- FastAPI 0.161.1
- LangChain 1.4.7
- langchain-core 1.7.0
- langchain-openai 1.7.2
- NumPy 2.5.4

## 自动化测试

```text
pytest：23 passed
ruff check：通过
浏览器交互：26/26 通过
```

覆盖：

- 健康检查与 5 份种子文档；
- 登录、错误密码和未认证访问；
- view/operator/admin 三类角色；
- 文档可见范围；
- 文档上传、扩展名校验和删除；
- RAG 引用；
- 订单工具调用与只读用户拦截；
- 工单草稿、确认和幂等；
- SSE 事件；
- 会话所有权；
- 操作审计；
- LangChain `create_agent` 的模拟工具调用循环；
- LangChain 流式事件输出与消息去重；
- DeepSeek 与自定义 OpenAI-Compatible 供应商配置解析；
- RAG 固定评测 10/10。

工程验证：

- `pip install -e ".[dev]"` 成功；
- `pip check` 无依赖冲突；
- wheel 构建成功，静态页面和 5 份种子文档已包含在安装包中；
- `docker compose config --quiet` 配置解析通过；
- Docker daemon 当前未启动，因此镜像构建和容器启动尚未验证。

浏览器验证：

- 管理员登录后可见 5 篇文档、上传入口和评测入口；
- RAG 回答包含“5 次”和账号策略引用；
- 订单工具返回运输中；
- 工单只生成 `DRF-*` 待确认草稿；
- 页面评测显示 100% 和 10/10；
- 只读用户只看到 2 篇公开文档，订单查询被拦截；
- 客服角色可见 4 篇文档，不显示管理功能；
- 所有 API 请求均为 HTTP 200，无 JavaScript 异常；
- 截图保存在 `docs/ui-dashboard.png`。

DeepSeek 配置浏览器验证：

- 使用 `LLM_PROVIDER=deepseek` 启动；
- 页面运行模式显示 `DEEPSEEK` 和 `DEEPSEEK Agent`；
- 登录、文档和运行状态接口均为 HTTP 200；
- 无 JavaScript 异常，5/5 断言通过。

真实 DeepSeek 联调：

- `runtime` 返回 `llm_mode=langchain-agent`、`llm_provider=deepseek`、
  `llm_model=deepseek-chat`、`embedding_mode=hash`；
- RAG 问答使用 `langchain-agent`，`fallback=false`，返回 4 条来源；
- 订单问题由模型调用 `query_order_status`，回答包含“运输中”；
- SSE 返回 52 个 `token` 事件和 1 个 `done` 事件；
- 联调使用临时 SQLite 数据库，结束后已删除。

## 尚未验证

- OpenAI Embedding 适配器已实现，当前测试使用离线哈希 Embedding；
- Docker 镜像需要在 Docker daemon 启动后重新执行构建验证；

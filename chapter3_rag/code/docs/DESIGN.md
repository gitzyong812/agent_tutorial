# 第 3 章配套代码整体设计

本文档面向后续开发者，说明 `agent_book/chapter3_rag/code` 当前代码库的已有功能、整体技术架构、文件组织方式，以及“功能模块”和“技术实现”的对应关系。

这个项目是一个本地教学系统，不是生产系统。它的核心目标是让学生在一个最小可运行的网页应用中理解三件事。

1. 基础 ChatBot 如何由模型配置、数字员工配置、短期历史和流式回复组成。
2. RAG 如何在对话前增加知识检索，把文档片段作为回答依据。
3. 一个可扩展的数字员工框架如何把配置、运行时、知识库和前端页面解耦。

## 1. 项目定位

本项目是第 3 章“知识增强的 RAG 数字员工”的配套代码。它继承了第 2 章基础 ChatBot 的能力，并在此基础上增加知识库、分块、索引、检索、引用资料展示和引用资料持久化。

当前系统包含四个主功能区。

| 功能区 | 面向用户的能力 | 后端核心模块 | 前端核心文件 |
| --- | --- | --- | --- |
| 对话 | 新建会话、选择数字员工、流式聊天、查看历史消息和引用资料 | `routers/chat.py`、`runners/`、`llm.py` | `static/js/chat.js` |
| 知识库 | 管理标签、文档、分块预览、重建索引、检索调试 | `routers/knowledge.py`、`rag/` | `static/js/knowledge.js` |
| 模型配置 | 配置和测试 OpenAI 兼容对话模型 | `routers/model_configs.py`、`llm.py` | `static/js/models.js` |
| 数字员工 | 配置 ChatBot 或 RAG 数字员工，设置提示词和模型参数 | `routers/agents.py`、`models.py` | `static/js/agents.js` |

系统的教学重点是“流程透明”。因此代码没有引入复杂框架，也没有隐藏关键逻辑。模型调用、提示词拼接、分块、检索和 SSE 解析都尽量放在清晰的小模块中。

## 2. 技术选型

| 技术 | 当前用途 | 选择原因 |
| --- | --- | --- |
| FastAPI | 后端 HTTP API 和 SSE 流式响应 | 写法清晰，适合教学和快速调试 |
| SQLAlchemy | ORM 和数据库会话管理 | 数据模型明确，便于观察表结构 |
| SQLite | 本地数据库 | 零服务依赖，适合课堂环境 |
| Pydantic | 请求和响应模型 | API 输入输出结构清晰 |
| OpenAI SDK | 调用 OpenAI 兼容 chat 和 embedding 接口 | 统一接入 DeepSeek、Qwen、OpenAI 等兼容服务 |
| numpy | 向量余弦相似度计算 | 小规模向量检索足够简单 |
| rank_bm25 | 关键词 BM25 检索 | 纯 Python 依赖，便于教学对比 |
| 原生 HTML/CSS/JS | 单页前端 | 无构建步骤，学生容易运行和查看 |
| marked + DOMPurify | Markdown 渲染和 HTML 清洗 | 让模型回答支持 Markdown，同时降低前端注入风险 |

## 3. 运行时总览

项目启动命令：

```bash
uvicorn app.main:app --reload
```

应用入口是 `app/main.py`。启动时会完成以下工作。

1. 导入 `models`，让 SQLAlchemy 注册所有表。
2. 执行 `Base.metadata.create_all(bind=engine)` 自动建表。
3. 打开数据库会话，执行 `seed.seed(db)` 写入演示数据。
4. 注册模型配置、数字员工、对话、知识库四组路由。
5. 把 `app/static` 挂载到根路径，返回前端页面。

当前项目没有使用数据库迁移工具。教学阶段如果表结构变化，可以删除 `chatbot.db` 或按需要删表重建。长期维护或生产化时，应增加 Alembic 一类迁移机制。

## 4. 项目文件树与功能对应关系

下面的文件树只列出当前项目中有业务含义的文件，省略 Python 缓存和运行时生成文件。

```text
code/
├── README.md
├── DESIGN.md
├── DESIGN_RAG.md
├── requirements.txt
├── data/
│   ├── insurance_product1_for_children.md
│   ├── insurance_product2_for_old.md
│   └── insurance_product3_for_women.md
└── app/
    ├── __init__.py
    ├── main.py
    ├── config.py
    ├── database.py
    ├── models.py
    ├── schemas.py
    ├── seed.py
    ├── llm.py
    ├── routers/
    │   ├── __init__.py
    │   ├── model_configs.py
    │   ├── agents.py
    │   ├── chat.py
    │   └── knowledge.py
    ├── runners/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── chatbot.py
    │   └── rag.py
    ├── rag/
    │   ├── __init__.py
    │   ├── parser.py
    │   ├── chunker.py
    │   ├── embedding.py
    │   ├── indexer.py
    │   └── retriever.py
    └── static/
        ├── index.html
        ├── css/
        │   └── style.css
        ├── js/
        │   ├── app.js
        │   ├── chat.js
        │   ├── knowledge.js
        │   ├── models.js
        │   └── agents.js
        ├── locales/
        │   ├── zh.json
        │   ├── en.json
        │   └── ru.json
        └── vendor/
            ├── marked.min.js
            ├── marked.LICENSE.md
            ├── purify.min.js
            └── dompurify.LICENSE
```

### 4.1 根目录文件

| 文件 | 功能 |
| --- | --- |
| `README.md` | 面向学生，说明如何安装、启动、配置模型、完成本章任务 |
| `DESIGN.md` | 面向开发者，说明项目整体设计和代码结构 |
| `DESIGN_RAG.md` | 面向本章 RAG 增量，详细说明 RAG 链路 |
| `requirements.txt` | Python 依赖列表 |
| `data/*.md` | 示例保险产品资料，可作为课堂知识库材料 |

### 4.2 后端核心文件

| 文件 | 功能 |
| --- | --- |
| `app/main.py` | FastAPI 应用入口，建表、seed、注册路由、挂载静态前端 |
| `app/config.py` | 读取 `.env`，包括数据库地址、embedding 配置和分块参数 |
| `app/database.py` | 创建 SQLAlchemy engine、SessionLocal、Base 和请求级数据库依赖 |
| `app/models.py` | ORM 数据模型，包括模型配置、数字员工、会话消息、知识库表 |
| `app/schemas.py` | Pydantic 请求和响应模型，约束 API 输入输出 |
| `app/seed.py` | 空库首次启动时写入演示模型、数字员工、标签和示例文档 |
| `app/llm.py` | 对话模型调用、系统提示词拼接、流式生成、连接测试 |

### 4.3 路由文件

| 文件 | 功能 |
| --- | --- |
| `routers/model_configs.py` | 对话模型配置增删改查、启停、连接测试 |
| `routers/agents.py` | 数字员工配置增删改查、发布状态切换 |
| `routers/chat.py` | 会话管理、历史消息查询、发送消息、SSE 流式响应、消息持久化 |
| `routers/knowledge.py` | 标签、文档、上传、重建索引和检索调试 |

### 4.4 数字员工运行时文件

| 文件 | 功能 |
| --- | --- |
| `runners/base.py` | 定义 `AgentRunner` 基类，提供短期历史截取逻辑 |
| `runners/chatbot.py` | 基础 ChatBot 运行时，组装系统提示词、历史消息和用户输入 |
| `runners/rag.py` | RAG 运行时，负责检索规划、检索调用、RAG 提示词拼接 |
| `runners/__init__.py` | 注册 `agent_type` 到 Runner 的映射 |

### 4.5 RAG 核心文件

| 文件 | 功能 |
| --- | --- |
| `rag/parser.py` | 文档类型识别和文本清洗 |
| `rag/chunker.py` | 文档分块，支持 `structure` 和 `fixed` |
| `rag/embedding.py` | 读取 embedding 配置，调用 OpenAI 兼容 `/embeddings` |
| `rag/indexer.py` | 文档重建索引，完成清洗、分块、embedding 和 chunk 写库 |
| `rag/retriever.py` | 检索统一入口，支持向量、关键词、混合检索和降级 |

### 4.6 前端文件

| 文件 | 功能 |
| --- | --- |
| `static/index.html` | 前端页面骨架，包含左侧导航和四个页面容器 |
| `static/css/style.css` | 页面整体样式、表格、弹窗、聊天气泡、引用资料折叠区 |
| `static/js/app.js` | 全局语言包加载、导航切换、通用 `fetch` 封装 |
| `static/js/chat.js` | 对话页、会话列表、SSE 解析、Markdown 渲染、引用资料恢复 |
| `static/js/knowledge.js` | 知识库页、标签管理、文档管理、检索调试 |
| `static/js/models.js` | 模型配置页 |
| `static/js/agents.js` | 数字员工配置页，含 RAG 配置区 |
| `static/locales/*.json` | 中、英、俄界面文案 |
| `static/vendor/*` | 前端第三方库和许可证 |

## 5. 整体技术架构

系统可以分为五层。

```text
浏览器单页前端
    |
    | JSON API / SSE
    v
FastAPI 路由层
    |
    | 调用服务模块和运行时
    v
业务运行层
    |
    | ORM 读写
    v
SQLite 数据层
    |
    | 外部 HTTP
    v
OpenAI 兼容模型服务
```

### 5.1 浏览器单页前端

前端只负责交互和展示，不保存业务状态。它通过 `App.api` 调用后端 JSON API，通过 `fetch` 读取 SSE 流。

前端的重要职责包括：

- 渲染模型配置、数字员工、知识库和对话页面。
- 把表单内容组织为 JSON 请求体。
- 解析 SSE 事件，把回答 token 逐步显示到聊天气泡中。
- 在 RAG 回答中展示引用资料。
- 刷新历史会话时，从 `extra.rag_sources` 恢复引用资料区。

### 5.2 FastAPI 路由层

路由层负责 HTTP 协议、参数接收、错误响应和响应模型。它不直接实现复杂算法，而是把工作交给 ORM、Runner、RAG 模块或 LLM 模块。

例如：

- `model_configs.py` 调用 `llm.test_model_config` 测试模型。
- `chat.py` 调用 `runners.get_runner` 获取运行时。
- `knowledge.py` 调用 `indexer.reindex_document` 重建索引。
- `knowledge.py` 调用 `retriever.search` 做检索调试。

### 5.3 业务运行层

业务运行层包括 `llm.py`、`runners/` 和 `rag/`。

`llm.py` 面向模型调用，封装 chat completions 的流式和非流式调用。

`runners/` 面向数字员工类型，决定一次对话应该如何组装消息。

`rag/` 面向知识处理，负责文档进入知识库后的清洗、分块、向量化、检索和降级。

### 5.4 数据层

数据层使用 SQLite。所有表由 SQLAlchemy ORM 定义，启动时自动建表。

当前持久化的数据包括：

- 对话模型配置。
- 数字员工配置。
- 会话和消息。
- 知识标签。
- 知识文档。
- 知识片段及其向量。

### 5.5 外部模型服务

系统调用两类 OpenAI 兼容接口。

- 对话模型：由前端“模型配置”页面维护，写入 `model_configs` 表。
- embedding 模型：由 `.env` 维护，启动时通过 `config.py` 读取。

这样设计是为了让学生清楚看到“生成回答”和“生成向量”是两个不同任务。

## 6. 功能模块和技术实现对应关系

### 6.1 模型配置模块

面向功能：

- 新建对话模型配置。
- 编辑 `provider`、`base_url`、`model_name`、`api_key`。
- 启用或停用配置。
- 测试模型连接。

技术实现：

| 层次 | 文件 | 说明 |
| --- | --- | --- |
| 前端 | `static/js/models.js` | 渲染模型列表和表单，调用模型配置 API |
| API | `routers/model_configs.py` | 提供增删改查、启停、测试接口 |
| 数据模型 | `models.py` 的 `ModelConfig` | 保存模型服务连接信息 |
| 请求响应 | `schemas.py` 的 `ModelConfigIn`、`ModelConfigOut`、`ActiveIn` | 定义接口结构 |
| 模型调用 | `llm.py` 的 `test_model_config` | 发起一次最小 chat completions 测试 |

当前接口：

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| `GET` | `/api/model-configs` | 列出 chat 类型模型配置 |
| `POST` | `/api/model-configs` | 创建模型配置 |
| `PUT` | `/api/model-configs/{config_id}` | 更新模型配置 |
| `DELETE` | `/api/model-configs/{config_id}` | 删除模型配置 |
| `PATCH` | `/api/model-configs/{config_id}/active` | 启用或停用 |
| `POST` | `/api/model-configs/{config_id}/test` | 测试连接 |

需要注意：当前接口会强制前端维护的配置为 `config_type="chat"`。embedding 配置不通过这个页面管理。

### 6.2 数字员工配置模块

面向功能：

- 创建基础 ChatBot 或 RAG 数字员工。
- 配置角色、目标、约束、输出要求。
- 配置 temperature、top_p、max_tokens 等模型参数。
- 配置短期历史轮数。
- 对 RAG 类型配置绑定标签、top_k 和检索器类型。
- 发布或下线数字员工。

技术实现：

| 层次 | 文件 | 说明 |
| --- | --- | --- |
| 前端 | `static/js/agents.js` | 渲染数字员工列表和配置弹窗 |
| API | `routers/agents.py` | 数字员工增删改查和状态切换 |
| 数据模型 | `models.py` 的 `AgentConfig` | 保存提示词要素、模型参数、RAG 参数 |
| 请求响应 | `schemas.py` 的 `AgentConfigIn`、`AgentConfigOut`、`StatusIn` | 定义接口结构 |
| 运行时分派 | `runners/__init__.py` | 按 `agent_type` 分派到不同 Runner |

当前接口：

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| `GET` | `/api/agents` | 列出数字员工，可按状态过滤 |
| `POST` | `/api/agents` | 创建数字员工 |
| `GET` | `/api/agents/{agent_id}` | 获取详情 |
| `PUT` | `/api/agents/{agent_id}` | 更新配置 |
| `DELETE` | `/api/agents/{agent_id}` | 删除数字员工 |
| `PATCH` | `/api/agents/{agent_id}/status` | 发布或下线 |

### 6.3 会话与对话模块

面向功能：

- 列出历史会话。
- 新建会话。
- 删除会话。
- 查看会话消息。
- 发送用户消息。
- 接收助手流式回答。
- RAG 回答展示引用资料。
- 刷新页面后恢复历史回答和引用资料。

技术实现：

| 层次 | 文件 | 说明 |
| --- | --- | --- |
| 前端 | `static/js/chat.js` | 会话列表、消息气泡、SSE 解析、引用资料展示 |
| API | `routers/chat.py` | 会话接口、消息接口、SSE 响应 |
| 数据模型 | `ConversationSession`、`ChatMessage` | 保存会话和消息 |
| 请求响应 | `ConversationIn`、`ConversationOut`、`MessageIn`、`MessageOut` | 定义会话和消息结构 |
| 运行时 | `runners/` | 根据数字员工类型组装模型消息 |
| 模型调用 | `llm.py` | 调用 chat completions 流式接口 |

当前接口：

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| `GET` | `/api/conversations` | 列出会话 |
| `POST` | `/api/conversations` | 新建会话，只能选择已发布数字员工 |
| `GET` | `/api/conversations/{session_id}/messages` | 获取历史消息 |
| `DELETE` | `/api/conversations/{session_id}` | 删除会话 |
| `POST` | `/api/conversations/{session_id}/messages` | 发送消息，返回 SSE 流 |

发送消息的后端流程：

1. `send_message` 接收 `MessageIn`。
2. 打开数据库会话，读取 `ConversationSession`、`AgentConfig`、`ModelConfig` 和历史消息。
3. 调用 `runners.get_runner(db, agent)` 获取运行时。
4. 调用 Runner 的 `build_messages` 得到 `messages` 和 `passages`。
5. 如果有 `passages`，先转换为 `sources`。
6. `event_stream` 先推送 `sources` 事件，再推送普通 token。
7. 流结束后 `_persist` 写入用户消息和助手消息。
8. 如果存在 sources，写入助手消息的 `extra.rag_sources`。

前端 SSE 处理逻辑：

1. `send` 先把用户消息插入页面。
2. 创建一个助手占位气泡。
3. `consumeStream` 读取 SSE 流。
4. 收到 `sources` 事件时解析 JSON 并渲染引用资料。
5. 收到普通 data 时累加答案并重新渲染 Markdown。
6. 收到 `done` 时结束本轮渲染。
7. 首轮对话后刷新左侧会话标题。

### 6.4 知识库模块

面向功能：

- 创建和删除标签。
- 查看文档列表。
- 按标签筛选文档。
- 按关键词搜索文档名和来源。
- 粘贴文本创建文档。
- 上传 `.txt`、`.md`、`.markdown` 文件。
- 编辑文档内容、来源、版本、有效期和标签。
- 查看分块预览。
- 重建索引。
- 直接调试检索结果。

技术实现：

| 层次 | 文件 | 说明 |
| --- | --- | --- |
| 前端 | `static/js/knowledge.js` | 知识库页面、文档弹窗、标签管理、检索调试 |
| API | `routers/knowledge.py` | 标签、文档、上传、reindex、search 接口 |
| 数据模型 | `KnowledgeTag`、`KnowledgeDocument`、`KnowledgeChunk` | 保存知识库数据 |
| 请求响应 | `TagIn`、`TagOut`、`DocumentIn`、`DocumentOut`、`DocumentDetailOut`、`SearchIn`、`PassageOut` | 定义知识库 API 结构 |
| 文档处理 | `rag/parser.py`、`rag/chunker.py`、`rag/indexer.py` | 清洗、分块、索引 |
| 检索 | `rag/retriever.py` | 向量、关键词、混合检索 |
| 向量化 | `rag/embedding.py` | 读取 `.env` 并调用 embedding 接口 |

当前接口：

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| `GET` | `/api/tags` | 标签列表 |
| `POST` | `/api/tags` | 创建标签 |
| `DELETE` | `/api/tags/{tag_id}` | 删除标签 |
| `GET` | `/api/documents` | 文档列表，支持 `tag_id` 和 `keyword` |
| `POST` | `/api/documents` | 创建文本知识文档 |
| `POST` | `/api/documents/upload` | 上传文档 |
| `GET` | `/api/documents/{document_id}` | 文档详情，含 chunk |
| `PUT` | `/api/documents/{document_id}` | 更新文档并重建索引 |
| `DELETE` | `/api/documents/{document_id}` | 删除文档及其 chunk |
| `POST` | `/api/documents/{document_id}/reindex` | 重建索引，可传 `strategy` |
| `POST` | `/api/knowledge/search` | 检索调试 |

### 6.5 RAG 运行模块

面向功能：

- 判断本轮问题是否需要检索。
- 把上下文追问改写为独立检索 query。
- 按数字员工绑定标签检索片段。
- 将检索片段拼入系统提示词。
- 在回答中要求模型只依据资料回答。
- 返回引用资料给前端。

技术实现：

| 层次 | 文件 | 说明 |
| --- | --- | --- |
| 运行时 | `runners/rag.py` | RAG 对话主流程 |
| 检索 | `rag/retriever.py` | 根据 query 和标签返回 Passage |
| 提示词 | `build_rag_prompt` | 拼接角色、规则、检索资料和语言要求 |
| 规划 | `build_rag_query` | 用轻量 LLM 调用判断是否检索，并生成 query |
| 降级 | `_fallback_rag_query` | 规划失败时按规则构造 query |

RAG 的关键流程：

1. `RagRunner.build_messages` 收到历史消息和用户输入。
2. `build_rag_query` 调用当前对话模型生成 JSON 计划。
3. 计划包括 `should_retrieve` 和 `query`。
4. 如果规划失败，使用 `_fallback_rag_query`。
5. 如果需要检索，调用 `retriever.search`。
6. `build_rag_prompt` 把检索资料写入系统提示词。
7. 返回 `messages` 和 `passages`。

## 7. 数据模型详细说明

### 7.1 `ModelConfig`

用途：保存对话模型连接配置。

主要字段：

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `name` | 配置名称 |
| `provider` | 服务商标识 |
| `base_url` | OpenAI 兼容接口地址 |
| `model_name` | 模型名 |
| `api_key` | API Key，当前明文存储 |
| `config_type` | 当前前端固定为 `chat` |
| `dimensions` | embedding 维度字段，当前前端不维护 |
| `is_active` | 是否启用 |
| `created_at`、`updated_at` | 时间戳 |

### 7.2 `AgentConfig`

用途：保存数字员工配置。

核心字段分为四组。

提示词要素：

- `role`
- `service_goal`
- `business_context`
- `constraints`
- `output_instruction`

模型调用参数：

- `temperature`
- `top_p`
- `max_tokens`
- `frequency_penalty`
- `presence_penalty`

对话控制：

- `history_turns`
- `status`
- `extensions`

RAG 参数：

- `agent_type`
- `knowledge_tag_ids`
- `retrieval_top_k`
- `retriever_type`

### 7.3 `ConversationSession`

用途：保存一次连续对话会话。

主要字段：

| 字段 | 说明 |
| --- | --- |
| `title` | 会话标题，首轮消息后用用户输入前 20 字回填 |
| `agent_config_id` | 会话绑定的数字员工 |
| `language` | 回答语言，当前支持 `zh`、`en`、`ru` |
| `messages` | 关联的消息列表 |

### 7.4 `ChatMessage`

用途：保存一条用户或助手消息。

主要字段：

| 字段 | 说明 |
| --- | --- |
| `session_id` | 所属会话 |
| `role` | `user` 或 `assistant` |
| `content` | 消息正文 |
| `extra` | 附加 JSON 元数据 |
| `created_at` | 创建时间 |

`extra` 当前用于保存 RAG 引用资料。

```json
{
  "rag_sources": [
    {
      "document_id": 1,
      "document_name": "示例健康保障计划知识库",
      "source_title": "等待期",
      "embedding_model_name": "",
      "content": "...",
      "score": 1.0
    }
  ]
}
```

### 7.5 `KnowledgeTag`

用途：为文档归类，并作为 RAG 数字员工绑定知识范围的依据。

主要字段：

- `id`
- `name`
- `created_at`

### 7.6 `KnowledgeDocument`

用途：保存知识文档全文和索引状态。

主要字段：

| 字段 | 说明 |
| --- | --- |
| `name` | 文档名称 |
| `source` | 来源，例如文件名或备注 |
| `version` | 版本 |
| `content` | 清洗前的文档正文来源 |
| `file_type` | 当前支持 `markdown` 和 `txt` |
| `status` | `pending`、`indexed`、`failed` |
| `expires_at` | 过期时间，空表示长期有效 |
| `chunk_count` | 当前 chunk 数量 |
| `tags` | 多对多标签 |
| `chunks` | 关联的分块结果 |

### 7.7 `KnowledgeChunk`

用途：保存检索的最小单元。

主要字段：

| 字段 | 说明 |
| --- | --- |
| `document_id` | 所属文档 |
| `chunk_index` | 文档中的顺序 |
| `content` | 片段正文 |
| `source_title` | 来源标题 |
| `embedding` | 向量 JSON，缺失时为空 |
| `embedding_model_name` | 向量来自哪个模型 |
| `meta` | 预留元数据 |

## 8. 主要业务流程

### 8.1 启动与 seed 流程

```text
uvicorn app.main:app --reload
    |
    v
导入 app/main.py
    |
    v
导入 models 注册 ORM
    |
    v
create_all 自动建表
    |
    v
seed.seed(db)
    |
    v
注册 API 路由并挂载前端
```

`seed.seed` 只在空库时写入数据。判断依据是是否已经存在任意 `ModelConfig`。

首次写入内容包括：

- 示例对话模型配置。
- “保险条款”标签。
- 示例健康保障计划知识库文档。
- “高情商话术改写助手” ChatBot 草稿。
- “保险知识问答助手” RAG 草稿。

写入示例文档后会调用 `indexer.reindex_document`。如果没有 embedding 配置，文档会进入 `failed` 状态，但 chunk 仍会保存，后续可用于关键词检索。

### 8.2 基础 ChatBot 对话流程

```text
用户发送消息
    |
    v
routers/chat.py:send_message
    |
    v
runners.get_runner -> ChatbotRunner
    |
    v
llm.build_system_prompt
    |
    v
拼接 system + 最近历史 + 当前 user
    |
    v
llm.stream_chat
    |
    v
SSE 推送 token
    |
    v
_persist 写入 user 和 assistant 消息
```

基础 ChatBot 的事实来源主要是 `AgentConfig.business_context`。`llm.build_system_prompt` 会把角色、目标、业务资料、约束和输出要求拼成系统提示词，并补充“资料未覆盖时不要编造”的通用规则。

### 8.3 RAG 对话流程

```text
用户发送消息
    |
    v
routers/chat.py:send_message
    |
    v
runners.get_runner -> RagRunner
    |
    v
build_rag_query 生成检索计划
    |
    v
retriever.search 检索知识片段
    |
    v
build_rag_prompt 拼接 RAG 系统提示词
    |
    v
chat.py 先推送 sources 事件
    |
    v
llm.stream_chat 推送回答 token
    |
    v
_persist 写入消息，并保存 extra.rag_sources
```

RAG 类型与基础 ChatBot 的关键区别是：业务事实不再主要来自 `business_context`，而是来自检索资料。`business_context` 在前端 RAG 表单中被隐藏，避免学生继续把资料写死在提示词里。

### 8.4 文档入库和索引流程

```text
前端创建或编辑文档
    |
    v
routers/knowledge.py
    |
    v
写入 KnowledgeDocument 和标签关系
    |
    v
indexer.reindex_document
    |
    v
parser.clean_text
    |
    v
chunker.split_text
    |
    v
embedding.embed_texts
    |
    v
删除旧 KnowledgeChunk
    |
    v
写入新 KnowledgeChunk
    |
    v
更新 document.status 和 chunk_count
```

索引阶段有一个重要设计：embedding 失败不阻断文档入库。文档会标记为 `failed`，chunk 仍保存。检索时如果向量不可用，会回退到关键词检索。

### 8.5 检索调试流程

```text
前端检索调试弹窗
    |
    v
POST /api/knowledge/search
    |
    v
retriever.search
    |
    v
加载候选 chunk
    |
    v
按 retriever_type 执行检索
    |
    v
返回 PassageOut 列表
```

检索调试接口不调用生成模型。它只返回命中片段，适合课堂上观察“为什么模型回答前先要看检索是否命中”。

## 9. RAG 检索细节

### 9.1 候选片段过滤

`retriever._load_candidate_chunks` 会先根据文档有效期和标签过滤候选片段。

过滤规则：

1. 文档 `expires_at` 为空，表示长期有效。
2. 文档 `expires_at` 晚于当前时间，表示仍有效。
3. 如果传入 `tag_ids`，文档必须命中其中至少一个标签。
4. 如果 `tag_ids` 为空，不限制标签，主要用于检索调试。

### 9.2 向量检索

`_vector_search` 的流程：

1. 读取 `.env` 中的 embedding 配置。
2. 从候选 chunk 中筛选已有 embedding 的片段。
3. 对 query 调用 embedding。
4. 使用 numpy 计算 query 向量和 chunk 向量的余弦相似度。
5. 按分数倒序取 top_k。

如果配置缺失、chunk 无向量或 query embedding 调用失败，返回 `None`，由外层回退到关键词检索。

### 9.3 关键词检索

`_keyword_search` 的流程：

1. 对 query 和 chunk 做简单分词。
2. 优先使用 `rank_bm25.BM25Okapi`。
3. 如果 BM25 不可用，则用词项命中次数作为分数。
4. 分数大于 0 的片段才返回。

中文目前按单字切分，英文和数字按连续片段切分。这是教学实现，不是完整中文搜索方案。

### 9.4 混合检索

`hybrid` 会同时执行向量检索和关键词检索，然后用 RRF 融合。

如果两路都有结果，使用 `_rrf_merge` 排序并去重。如果只有一路有结果，直接使用那一路。

## 10. 提示词设计

### 10.1 基础 ChatBot 提示词

基础 ChatBot 使用 `llm.build_system_prompt`。

拼接顺序为：

1. 角色。
2. 任务目标。
3. 业务资料。
4. 约束条件。
5. 输出要求。
6. 通用规则。
7. 语言要求。

这个提示词适合演示第 2 章的基本能力：通过可配置提示词和短期历史构建一个通用 ChatBot。

### 10.2 RAG 提示词

RAG 使用 `runners/rag.py` 中的 `build_rag_prompt`。

拼接顺序为：

1. 角色。
2. 任务目标。
3. 约束条件。
4. 输出要求。
5. 回答规则。
6. 检索资料。
7. 语言要求。

RAG 提示词刻意不加入 `business_context`。它要求模型只能依据“检索资料”回答。如果资料缺失，必须说明无法确认并建议人工核实。

## 11. 前端交互设计

### 11.1 页面组织

`index.html` 中定义一个左侧导航和四个内容区。

- `page-chat`
- `page-knowledge`
- `page-models`
- `page-agents`

`app.js` 的 `switchTab` 会根据导航项切换页面，并调用对应页面对象的 `render` 方法。每次切换都重新请求数据，避免页面展示旧状态。

### 11.2 API 调用

普通 JSON 请求统一通过 `App.api(method, url, body)`。

这个函数负责：

- 设置 `Content-Type: application/json`。
- 序列化请求体。
- 检查 HTTP 状态码。
- 从后端错误响应中读取 `detail`。
- 返回 JSON 数据。

SSE 对话流没有使用 `App.api`，而是在 `chat.js` 中直接调用 `fetch`，因为它需要读取 `ReadableStream`。

### 11.3 对话页

`chat.js` 管理以下状态：

- `currentId`：当前会话 id。
- `published`：可新建会话的已发布数字员工。
- `sessions`：会话列表。
- `agentInfo`：数字员工和模型名称查找表。

主要方法：

- `render`：渲染会话布局。
- `openNewSession`：显示新会话表单。
- `openSession`：加载历史消息。
- `send`：发送当前输入。
- `consumeStream`：解析 SSE。
- `sourcesHtml`：渲染引用资料折叠区。
- `renderAssistant`：渲染助手消息和 Markdown。

### 11.4 知识库页

`knowledge.js` 管理文档、标签、上传和检索调试。

它的关键设计是：上传文件后不直接调用上传接口写库，而是读取文件文本，打开文档表单，让学生能看到和编辑内容后再保存。这更符合教学场景。

### 11.5 数字员工页

`agents.js` 根据 `agent_type` 控制表单展示。

- `chatbot`：显示业务资料字段。
- `rag_chatbot`：隐藏业务资料字段，显示标签、top_k 和检索器类型。

这体现了功能边界：ChatBot 通过静态业务资料回答，RAG 通过知识库检索资料回答。

## 12. 日志设计

项目使用标准库 `logging`，logger 名称为 `uvicorn.error`，这样日志会和 uvicorn 的输出显示在一起。

当前日志重点记录关键流程节点。

| 位置 | 日志内容 |
| --- | --- |
| `main.py` | 应用启动、数据库地址、静态目录 |
| `chat.py` | 会话创建、消息接收、Runner 准备、sources 推送、消息持久化、流式异常 |
| `runners/rag.py` | 检索规划、检索结果、规划失败降级 |
| `rag/indexer.py` | 文档重建索引开始、embedding 缺失或失败、索引完成 |
| `rag/retriever.py` | 候选片段数量、向量降级、关键词检索、混合检索 |

日志的目标是帮助学生和开发者判断问题发生在哪个环节。例如：

- 没有引用资料，应先看是否有 `rag retrieved` 日志。
- 文档状态为 `failed`，应看是否有 embedding 配置缺失或调用失败日志。
- 对话失败，应看 `stream failed` 后面的异常堆栈。

## 13. 配置和环境

### 13.1 数据库配置

默认数据库地址：

```text
sqlite:///./chatbot.db
```

这个路径相对于启动命令所在目录。因此建议始终在 `agent_book/chapter3_rag/code` 下启动服务。

可以通过 `.env` 覆盖：

```bash
APP_DATABASE_URL=sqlite:///./chatbot.db
```

### 13.2 对话模型配置

对话模型配置在前端“模型配置”页面维护，最终写入 `model_configs` 表。

当前模型接口使用 OpenAI 兼容 chat completions。只要服务支持同类接口，就可以作为对话模型使用。

### 13.3 Embedding 配置

embedding 配置通过 `.env` 维护。

```bash
EMBEDDING_BASE_URL=https://your-compatible-endpoint
EMBEDDING_MODEL_NAME=your-embedding-model
EMBEDDING_API_KEY=your-api-key
EMBEDDING_DIMENSIONS=
```

如果修改 `.env`，需要重启服务。已有文档需要重建索引后才会重新生成向量。

### 13.4 分块参数

```bash
DEFAULT_CHUNK_SIZE=400
DEFAULT_BATCH_SIZE=10
```

`DEFAULT_CHUNK_SIZE` 控制默认分块大小。`DEFAULT_BATCH_SIZE` 控制 embedding 批量请求数量。

## 14. 当前限制

当前实现刻意保持简单，因此存在以下限制。

- 没有用户体系，所有数据默认本地共享。
- API Key 明文保存在 SQLite 中，只适合本地教学。
- 没有数据库迁移机制，表结构变化需要手动处理。
- SQLite 不适合多人并发写入和大规模知识库。
- 向量直接存 JSON，不适合大规模检索。
- 中文关键词检索只是教学级实现。
- 文件解析只支持文本和 Markdown。
- `.env` 修改后需要重启服务。
- RAG 检索规划依赖对话模型，模型异常时会回退到规则检索。
- 没有后台任务队列，文档索引在请求过程中同步执行。

## 15. 扩展建议

### 15.1 新增数字员工类型

建议路径：

1. 在 `app/runners/` 新增一个 Runner 文件。
2. 继承 `AgentRunner`。
3. 实现 `build_messages`。
4. 在 `runners/__init__.py` 的 `_RUNNERS` 中注册新的 `agent_type`。
5. 在 `schemas.py` 和前端 `agents.js` 中补充必要配置字段。

这种扩展方式可以避免修改 `chat.py` 的主流程。

### 15.2 新增文件格式

建议路径：

1. 扩展 `rag/parser.py` 的 `detect_file_type`。
2. 增加对应文件解析逻辑。
3. 修改前端上传文件的 `accept` 类型。
4. 在 README 和 DESIGN_RAG 中说明新格式。

PDF、Word、OCR 都适合沿这条线扩展。

### 15.3 接入向量数据库

建议路径：

1. 保留 `retriever.search` 的统一入口。
2. 替换 `_vector_search` 的内部实现。
3. 让 `KnowledgeChunk` 继续保存可展示的原文和来源信息。
4. 把外部向量库 id 放入 `KnowledgeChunk.meta`。

这样可以保持前端引用资料展示和 RAG 提示词逻辑不变。

### 15.4 增加后台索引任务

当前索引同步执行。文档变大后，可以把 `indexer.reindex_document` 放入后台任务或队列。

扩展时要注意：

- 文档状态需要区分 `pending`、`indexing`、`indexed`、`failed`。
- 前端需要轮询或手动刷新状态。
- 失败原因最好写入文档元数据，便于排查。

### 15.5 增加生产级安全能力

如果要从教学项目走向真实系统，至少需要补充：

- 用户登录和权限。
- API Key 加密存储。
- 数据库迁移。
- 请求限流。
- 文件大小限制。
- 上传内容安全检查。
- 模型调用超时和重试策略。
- 更细粒度的审计日志。

## 16. 开发者快速定位指南

如果遇到问题，可以按下面方式定位。

| 问题 | 优先查看 |
| --- | --- |
| 页面打不开 | `app/main.py`、uvicorn 启动日志、静态目录挂载 |
| 模型配置测试失败 | `static/js/models.js`、`routers/model_configs.py`、`llm.py` |
| 无法发布或选择数字员工 | `routers/agents.py`、`routers/chat.py`、`AgentConfig.status` |
| 对话没有流式输出 | `routers/chat.py`、`llm.stream_chat`、浏览器网络面板 |
| RAG 没有引用资料 | `runners/rag.py`、`rag/retriever.py`、`chat.py` 的 sources 事件 |
| 刷新后引用资料消失 | `ChatMessage.extra`、`MessageOut.extra`、`chat.js` 的 `m.extra?.rag_sources` |
| 文档保存后状态 failed | `.env` embedding 配置、`rag/indexer.py` 日志 |
| 检索没有命中 | `knowledge.js` 检索调试、`retriever._load_candidate_chunks`、标签绑定和文档有效期 |
| 分块不符合预期 | `rag/chunker.py`、文档 Markdown 标题结构 |
| 历史上下文太长或太短 | `AgentConfig.history_turns`、`AgentRunner.recent_history` |

## 17. 设计原则

当前代码遵循几个简单原则。

1. 配置和运行分离。模型配置、数字员工配置、知识库内容都存在数据库中，运行时只读取配置并执行。
2. ChatBot 和 RAG 分离。基础 ChatBot 不关心检索，RAG 逻辑集中在 `RagRunner` 和 `rag/` 目录。
3. 前端保持轻量。没有构建工具，所有页面都是原生 JS 对象。
4. 失败可降级。embedding 不可用时仍保存 chunk，并回退关键词检索。
5. 依据可追溯。RAG 回答不仅展示引用资料，还把引用资料持久化到消息中。
6. 便于扩展。新增数字员工类型、检索器、文件解析器时，应尽量沿现有模块边界扩展，而不是把逻辑塞进路由函数。

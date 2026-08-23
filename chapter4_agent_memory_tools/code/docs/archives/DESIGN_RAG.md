# 第 3 章 RAG 增量设计

本文档只说明本章相对基础 ChatBot 增加的 RAG 设计。整体项目结构、通用会话流程和前端组织见 `DESIGN.md`。

## 1. 增量目标

第 2 章的基础 ChatBot 主要依赖静态提示词和短期历史。第 3 章增加“检索”环节，让数字员工能从知识库中找依据，再基于依据回答。

本章目标包括四点。

1. 让学生理解 RAG 的基本链路：文档、分块、向量化、检索、生成、引用展示。
2. 保持最小可运行，即使没有 embedding 配置，也能通过关键词降级跑通流程。
3. 让 RAG 能复用原有模型配置、数字员工配置、会话和流式对话框架。
4. 为后续章节扩展工具、记忆、多 Agent 或外部检索服务保留边界。

## 2. 本章新增能力

- 知识标签：用标签组织文档，RAG 数字员工通过标签限定检索范围。
- 知识文档：支持粘贴文本和上传 `.txt`、`.md` 文件。
- 文档分块：支持结构优先分块和固定长度分块。
- 文档索引：分块后可调用 embedding 服务生成向量，并保存到 SQLite。
- 知识检索：支持 `vector`、`keyword`、`hybrid` 三种检索器。
- 检索调试：可在前端直接输入 query，观察命中的片段和分数。
- RAG 对话：对话前检索资料，生成回答时强制依据检索资料。
- 引用持久化：引用资料保存到 `ChatMessage.extra.rag_sources`，刷新页面后仍可展示。

## 3. 数据模型增量

### 3.1 `KnowledgeTag`

标签用于组织文档，也是 RAG 数字员工绑定知识范围的入口。

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `name` | 标签名，唯一 |
| `created_at` | 创建时间 |

### 3.2 `KnowledgeDocument`

文档保存清洗后的全文和检索相关元数据。

| 字段 | 说明 |
| --- | --- |
| `name` | 文档名 |
| `source` | 来源说明，通常是文件名或备注 |
| `version` | 版本号 |
| `content` | 文档全文 |
| `file_type` | `markdown` 或 `txt` |
| `status` | `pending`、`indexed`、`failed` |
| `expires_at` | 过期时间，空表示长期有效 |
| `chunk_count` | 分块数量 |
| `tags` | 多对多标签 |

检索时只使用未过期文档。如果 `expires_at` 早于当前时间，该文档不会参与候选片段加载。

### 3.3 `KnowledgeChunk`

片段是检索的最小单位。

| 字段 | 说明 |
| --- | --- |
| `document_id` | 所属文档 |
| `chunk_index` | 文档内片段顺序 |
| `content` | 片段原文 |
| `source_title` | Markdown 标题或章节名 |
| `embedding` | 向量，embedding 失败时为空 |
| `embedding_model_name` | 生成该向量的模型名 |
| `meta` | 预留元数据 |

向量直接存入 SQLite 的 JSON 字段。这样重启服务后不需要重新建索引，适合小规模教学数据。

### 3.4 `AgentConfig` 的 RAG 字段

RAG 数字员工使用 `agent_type="rag_chatbot"`。

| 字段 | 说明 |
| --- | --- |
| `knowledge_tag_ids` | 绑定的标签 id 列表 |
| `retrieval_top_k` | 每次保留的片段数量 |
| `retriever_type` | `vector`、`keyword` 或 `hybrid` |

`business_context` 对 RAG 类型不再作为事实来源。事实信息应来自检索资料，提示词中的角色、目标、约束和输出要求仍然有效。

## 4. 知识库构建流程

文档创建或重建索引时，入口是 `app/rag/indexer.py` 的 `reindex_document`。

流程如下。

1. 读取 `KnowledgeDocument.content`。
2. 用 `parser.clean_text` 做轻量清洗。
3. 用 `chunker.split_text` 分块。
4. 从 `.env` 读取 embedding 配置。
5. 如果 embedding 配置完整，调用 `/embeddings` 生成向量。
6. 删除旧 chunk，写入新的 `KnowledgeChunk`。
7. 更新文档 `chunk_count` 和 `status`。

如果缺少 embedding 配置或远端调用失败，系统仍会保存文本片段，并把文档状态置为 `failed`。这不是致命错误，后续检索会自动降级到关键词匹配。学生仍然可以观察完整的 RAG 流程。

## 5. 分块策略

分块逻辑在 `app/rag/chunker.py`。

### 5.1 `structure`

默认策略。先按 Markdown 标题切分，再对过长段落按长度细分。每个片段保留 `source_title`，便于回答时展示引用来源。

适合有标题结构的产品说明、条款、FAQ、政策文档。

### 5.2 `fixed`

固定长度分块。按字符数切分，并设置重叠。

适合结构不明显的纯文本，也适合教学中对比“结构分块”和“固定分块”的检索效果。

默认分块长度由 `DEFAULT_CHUNK_SIZE` 控制，默认是 400。默认重叠是 60。

## 6. Embedding 配置

embedding 配置在 `.env` 中维护，不在前端页面维护。

需要配置的变量如下。

```bash
EMBEDDING_BASE_URL=https://your-compatible-endpoint
EMBEDDING_MODEL_NAME=your-embedding-model
EMBEDDING_API_KEY=your-api-key
EMBEDDING_DIMENSIONS=
```

`EMBEDDING_DIMENSIONS` 可以留空。部分服务要求显式传维度时再填写。

修改 `.env` 后需要重启 uvicorn。已经存在的文档也需要在“知识库”页面点击“重建索引”，才能生成新的向量。

## 7. 检索设计

统一检索入口是 `app/rag/retriever.py` 的 `search`。

输入包括：

- `query`
- `tag_ids`
- `top_k`
- `retriever_type`

输出是 `Passage` 列表，每个 `Passage` 包含文档名、标题、片段内容、分数和 embedding 模型名。

检索前会先加载候选片段。

1. 过滤过期文档。
2. 如果传入标签，只保留命中任一标签的文档。
3. 加载这些文档下的 chunk。

### 7.1 向量检索

`vector` 检索会对 query 生成向量，然后和候选 chunk 的向量做余弦相似度计算。

如果缺少 embedding 配置、chunk 没有向量，或 query 向量化失败，系统会自动回退到关键词检索。

### 7.2 关键词检索

`keyword` 检索优先使用 `rank_bm25`。如果依赖不可用或运行失败，会使用简单词项命中计数。

中文按单字切分，英文和数字按连续词切分。这个实现足够教学演示，但不是面向生产的中文检索方案。

### 7.3 混合检索

`hybrid` 会分别执行向量检索和关键词检索，再用 RRF 做融合排序。如果其中一路不可用，则使用另一路结果。

## 8. RAG 对话流程

RAG 对话运行时在 `app/runners/rag.py`。

一次 RAG 对话分为六步。

1. `build_rag_query` 使用当前对话模型做一次轻量规划。
2. 规划器判断本轮是否需要检索，并生成独立检索 query。
3. 如果规划失败，则使用回退规则。空输入不检索，短问题会拼接上一轮用户问题，其余问题默认检索。
4. 调用 `retriever.search` 获取片段。
5. `build_rag_prompt` 拼接角色、目标、约束、输出要求、回答规则和检索资料。
6. 调用 `llm.stream_chat` 流式生成回答。

RAG 系统提示词明确要求：

- 只能依据检索资料回答。
- 检索资料不足时要说明无法确认。
- 不得编造业务事实。
- 先给结论，再说明依据。
- 资料冲突时提示冲突并建议人工确认。

如果规划器判断本轮不需要检索，例如寒暄或感谢，提示词会允许模型按角色自然回复，但仍要求不要编造业务事实。

## 9. 引用资料展示与持久化

RAG 类型对话会在 SSE 流开始前先推送 `sources` 事件。

前端 `chat.js` 收到 `sources` 后，把片段渲染为助手消息下方的折叠引用区。随后 token 持续到达时，前端会保留已有 sources，避免引用区被增量渲染覆盖。

流结束后，后端把本轮用户消息和助手消息写入 `chat_messages`。如果有引用资料，助手消息会保存：

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

刷新页面后，`GET /api/conversations/{session_id}/messages` 返回 `extra` 字段，前端通过 `m.extra?.rag_sources` 重新渲染引用资料区。

## 10. 后端接口

RAG 相关接口集中在 `app/routers/knowledge.py`。

### 10.1 标签

- `GET /api/tags`
- `POST /api/tags`
- `DELETE /api/tags/{tag_id}`

### 10.2 文档

- `GET /api/documents`
- `POST /api/documents`
- `POST /api/documents/upload`
- `GET /api/documents/{document_id}`
- `PUT /api/documents/{document_id}`
- `DELETE /api/documents/{document_id}`
- `POST /api/documents/{document_id}/reindex`

`reindex` 接口支持 `strategy` 查询参数，可以传 `structure` 或 `fixed`。

### 10.3 检索调试

- `POST /api/knowledge/search`

请求体包含 `query`、`tag_ids`、`retriever_type`、`top_k`。该接口不调用生成模型，只返回检索命中的片段。

## 11. 前端增量

RAG 前端主要由两个页面承载。

### 11.1 知识库页面

文件是 `app/static/js/knowledge.js`。

功能包括：

- 文档列表。
- 标签筛选。
- 关键词搜索。
- 新建文档。
- 上传文本或 Markdown。
- 编辑文档、标签、有效期。
- 查看分块预览。
- 重建索引。
- 检索调试。
- 标签管理。

### 11.2 数字员工页面

文件是 `app/static/js/agents.js`。

当类型选择为 `rag_chatbot` 时，页面显示 RAG 配置区。

- 绑定标签。
- 设置 `top_k`。
- 选择检索器类型。

基础 ChatBot 的 `business_context` 字段在 RAG 类型下隐藏，避免学生把事实资料继续写死在提示词里。

## 12. 教学观察点

本章适合让学生重点观察以下现象。

1. 同一份文档用不同分块策略，命中的片段可能不同。
2. 向量检索依赖 embedding 配置，配置缺失时会自动降级。
3. 关键词检索对字面匹配敏感，向量检索更依赖语义相似度。
4. `top_k` 太小可能漏掉必要依据，太大可能引入干扰。
5. 过期文档不会参与检索。
6. 引用资料可以帮助检查回答是否真的来自知识库。
7. RAG 不能保证模型绝不出错，因此仍需要资料边界、拒答规则和人工核实提示。

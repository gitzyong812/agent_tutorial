# 第 5 章配套代码整体设计

本文档记录 `agent_book/chapter5_harness/code` 当前完整代码库的设计。系统从基础 ChatBot 逐步扩展到 RAG、ReActAgent、工具、记忆和 Harness，但在当前目录中，它们共同组成一个可以直接运行的教学系统，而不是彼此独立的章节样例。

各设计文档的职责如下：

| 文档 | 作用 |
| --- | --- |
| `docs/DESIGN.md` | 当前完整代码库的功能、架构、模块和数据设计 |
| `docs/DESIGN_Harness.md` | 第 5 章 Harness 工程新增能力的详细设计 |
| `docs/archives/DESIGN_Agent.md` | 第 4 章 ReAct、工具与记忆的历史增量设计 |
| `docs/archives/DESIGN_RAG.md` | 第 3 章 RAG 的历史增量设计 |

后续修改代码时，应以本文档描述当前状态，并在对应章节设计中说明增量原因，避免把总览文档写成单章实施计划。

## 1. 项目定位

本项目是一个本地教学用数字员工系统，目标是让学生在同一套代码中观察智能体能力如何逐层形成。

1. ChatBot 展示提示词、短期历史和流式回复。
2. RAG 展示知识入库、检索、引用和有依据回答。
3. ReActAgent 展示模型决策、工具调用、观察回填和最大步骤控制。
4. 记忆模块展示日记形成、核心记忆整理和跨会话检索。
5. Harness 展示技能、多通道、工具权限、人工确认和结构化审计。

系统强调结构清晰和流程可观察，不追求生产平台的功能规模。当前不包含账号认证、角色系统、真实即时通信平台、远程技能市场、操作系统沙箱、分布式任务队列和生产级事务恢复。

## 2. 总体架构

```text
网页 SPA / 命令行 CLI
        |
        v
FastAPI 路由与通道适配
        |
        v
统一 Harness 执行服务（`harness/service.py`）
        |
        +--> ChatbotRunner：基础对话
        +--> RagRunner：检索后生成
        +--> ReactRunner：工具循环与暂停恢复
        |
        +--> LLM 兼容接口
        +--> RAG 检索器
        +--> ToolRegistry / ToolPolicy
        +--> SkillRegistry
        +--> Memory Service
        |
        v
SQLite：配置、知识、会话、记忆、运行、人工请求与审计
```

网页和 CLI 只处理输入输出形式，不复制 Agent 逻辑。三种数字员工通过 Runner 分派，知识、工具、技能和记忆作为独立能力被 Runner 组合。SQLAlchemy 模型保存配置与运行事实，SSE 负责把回答、引用、轨迹和确认事件逐步推给调用端。

## 3. 功能区与代码映射

| 功能区 | 主要能力 | 后端模块 | 前端模块 |
| --- | --- | --- | --- |
| 对话 | 会话、流式回答、引用、轨迹、确认卡 | `routers/chat.py`、`harness/service.py`、`runners/` | `static/js/chat.js` |
| 知识库 | 标签、文档、分块、索引、检索调试 | `routers/knowledge.py`、`rag/` | `static/js/knowledge.js` |
| 工具管理 | 内置工具、自定义 HTTP 工具、风险策略 | `routers/tools.py`、`tools/` | `static/js/tools.js` |
| 技能管理 | 技能发现、对话创建、导入、编辑、删除与绑定 | `routers/skills.py`、`skills/` | `static/js/skills.js` |
| 系统监控 | 状态统计、等待事项、脱敏关键事件 | `routers/monitoring.py`、`harness/audit.py` | `static/js/monitoring.js` |
| 记忆管理 | 日记、核心记忆、整理与检索 | `routers/memories.py`、`memory/` | `static/js/memories.js` |
| 模型配置 | 对话模型、Embedding 模型及连通测试 | `routers/model_configs.py`、`llm.py` | `static/js/models.js` |
| 数字员工 | 类型、提示词、模型、知识、工具和技能绑定 | `routers/agents.py` | `static/js/agents.js` |

前端采用原生 HTML、CSS 和 JavaScript，不需要构建步骤。中文、英文和俄文文案保存在 `static/locales/`。

## 4. 数字员工与运行时

### 4.1 统一配置

`AgentConfig` 保存三类数字员工的公共配置：

- 模型连接引用和生成参数。
- 角色、任务目标、业务背景、约束和输出要求。
- 短期历史轮数和发布状态。
- RAG 使用的知识标签、检索数量和检索器类型。
- ReActAgent 使用的工具绑定、技能绑定、最大步骤和记忆开关。

前端只展示与当前类型有关的字段。后端仍负责校验模型、标签、工具和技能是否真实存在，不能依赖界面约束保证数据正确。

### 4.2 ChatBot

`ChatbotRunner` 把数字员工提示词、最近若干轮历史和本轮输入组装为模型消息，再通过兼容 OpenAI 的接口流式返回文本。它不检索知识，也不调用工具，是其他类型的最小基线。

### 4.3 RAG

`RagRunner` 在生成回答前，根据数字员工绑定的知识标签调用检索器。检索支持向量、关键词和混合方式。命中的片段既进入模型上下文，也通过 `sources` SSE 事件发送到前端，并保存在助手消息的 `extra.rag_sources` 中。

知识库采用“标签、文档、片段”三层结构。没有可用 Embedding 时，文档仍可分块入库，检索自动降级为关键词匹配。

### 4.4 ReActAgent

`ReactRunner` 使用模型原生 Tool Calling 协议执行“决策、行动、观察、再决策”循环。每次工具调用都保留原始 `tool_call_id`，工具结果作为 `tool` 消息回填。达到最大步骤后，系统停止继续调用工具，并根据已有观察生成总结。

ReActAgent 可以使用计划、计算、知识检索、记忆检索、自定义 HTTP 和人工协同工具。Harness 在这一循环外增加技能加载、风险策略和暂停恢复，详细规则见 `docs/DESIGN_Harness.md`。

## 5. 知识、工具、技能与记忆

### 5.1 知识

`KnowledgeTag` 用于圈定知识范围，`KnowledgeDocument` 保存文档正文和索引状态，`KnowledgeChunk` 保存可检索片段、来源标题和可选向量。文档重建索引时重新分块并刷新片段。

### 5.2 工具

`ToolConfig` 保存内置或 HTTP 工具定义，`ReActAgentTool` 保存数字员工与工具的绑定及局部参数。工具调用统一经过工具存在与绑定检查、JSON Schema 参数校验和风险策略判断。技能不会增加、删除或过滤工具。

内置工具包括：

- `plan`：为复杂任务生成结构化计划。
- `calculator`：安全计算算术表达式。
- `knowledge_search`：复用知识库检索器。
- `memory_search`：检索全局和当前数字员工记忆。
- `ask_human`：在缺少不可推断的关键信息，或用户明确愿意讨论且聚焦问题会实质影响结果时暂停并收集输入，默认每轮最多调用两次。
- `handoff_to_human`：当前任务无法继续时结束本轮并结构化交接。

自定义 HTTP 工具支持 GET 和 POST，设置固定超时，不跟随重定向，并限制返回结果长度。

### 5.3 技能

技能位于项目根目录 `skills/`，按 `builtin`、`imported` 和 `created` 区分内置、本地导入与对话创建三种来源。`SkillRegistry` 在发现阶段只读取 `SKILL.md` 的 frontmatter，模型激活技能后才加载完整正文。

技能只提供流程说明。可选的 `required-tools` 仅用于展示依赖提示，不会自动绑定工具，也不参与权限判断。系统内置三个保险通用技能和 `skill-creator`。ReActAgent 可以自动识别创建意图，也可以通过 `/skill-creator <query>` 显式激活，从当前会话文本生成 `created` 技能。创建使用 Harness 内部能力，不注册为普通工具。

本地上传保留参考资料、资源和脚本，但教学系统不执行上传脚本。created 技能可以原子更新说明和正文，但名称不可修改。imported 和 created 技能可以删除，删除时先暂存目录，再清理所有 Agent 绑定，失败时恢复目录。

### 5.4 记忆

记忆分为两层持久数据：

- `Diary` 按日期保存任务过程和结果，同一天持续更新。
- `CoreMemory` 从日记中整理出少量稳定事实和任务经验。

成功完成的 ReActAgent 任务可以异步更新日记。核心记忆既可由定时任务整理，也可在记忆管理页手工触发。`memory_search` 同时检索全局记忆和当前数字员工记忆。

## 6. Harness 运行主线

网页、CLI 和微信消息统一转换为 `StandardRequest`，字段为 `session_id`、`channel`、`sender_id` 和 `content`。请求进入 `harness/service.py` 后创建 `HarnessRun`，再交给对应 Runner。内部执行先产生结构化事件，网页和 CLI 再把事件序列化为 JSON SSE，微信工作线程则汇总文本事件后调用微信发送接口。

对于 ReActAgent，一次典型运行如下：

1. 读取数字员工配置和短期历史。
2. 模型根据名称和描述决定是否激活一个技能。
3. 程序独立读取数字员工绑定的工具，技能激活前后工具集合不变。
4. 只读工具自动执行，受限工具被拒绝。
5. 写工具创建 `ApprovalRequest`，保存运行状态并返回确认事件。
6. 批准或拒绝后，把决定结果作为工具观察回填原 ReAct 循环。
7. 完成后更新原助手消息，并写入脱敏审计事件。

这一部分的状态机、权限顺序和 CowAgent 参考映射见 `docs/DESIGN_Harness.md`。

## 7. 数据模型

数据表按职责分为五组：

| 分组 | 数据表 |
| --- | --- |
| 配置 | `model_configs`、`agent_configs`、`react_agent_tools`、`agent_skill_bindings`、`tool_configs`、`tool_policies` |
| 会话 | `conversation_sessions`、`chat_messages`、`conversation_channel_bindings` |
| 知识 | `knowledge_tags`、`knowledge_documents`、`knowledge_chunks`、`document_tags` |
| 记忆 | `diaries`、`core_memories` |
| Harness | `harness_runs`、`human_requests`、`approval_requests`、`audit_events` |

已有章节的业务表保持原字段不变，第 5 章通过新增关联表和运行表扩展能力。应用启动时执行 `Base.metadata.create_all`，可为已有 SQLite 数据库补齐新表。

## 8. API 与 SSE

API 按资源划分为模型、数字员工、会话、通道、知识库、工具、记忆、技能、Harness 和治理接口。网页对话保留 `/api/conversations/{id}/messages`，CLI 使用 `/api/harness/messages`，微信通过会话下的 `/channels/weixin` 接口完成扫码、状态查询和解绑，三者最终调用同一执行服务。

技能接口除查询外，还提供本地目录导入、created 更新以及 imported、created 删除。技能文件直接写入受控目录，不新增技能数据表。

每个 SSE 数据块都是统一 JSON 信封，事件约定如下：

| 事件 | 内容 |
| --- | --- |
| `text_delta` | 流式回答文本 |
| `sources` | RAG 或知识工具的引用资料 |
| `trace` | 思考、工具调用、结果、权限和确认轨迹 |
| `human_required` | 普通人工输入或工具授权 |
| `handoff` | 结构化转人工信息 |
| `error` | 当前运行错误 |
| `done` | `completed`、`pending`、`handoff` 或 `failed` 状态 |

历史消息在 `extra` 中保存引用、轨迹、运行状态和待确认信息，因此页面刷新后仍能恢复展示。

## 9. 启动、种子数据与配置

`app/main.py` 负责建表、初始化种子数据、挂载路由和静态前端。种子逻辑幂等补齐内置工具及其风险策略，为已有 ReActAgent 一次性补齐可解除的 `skill-creator`、`ask_human` 和 `handoff_to_human` 默认绑定。用户解除后，重启不会再次恢复。

模型服务在管理页配置。Embedding 和记忆定时任务使用 `.env` 中的配置。API Key 为便于教学仍保存在本地 SQLite 中，因此项目只能用于受信任的本地环境。

## 10. 测试与维护边界

测试使用独立 SQLite 文件，并模拟模型和工具响应，不调用真实模型或外部服务。主要覆盖：

- ChatBot、RAG 和 ReAct 原有行为。
- 知识分块、检索和引用持久化。
- 工具协议、HTTP 边界和最大步骤。
- 日记、核心记忆和检索。
- 三类技能来源、对话创建、编辑删除、技能工具解耦和三种风险策略。
- 写操作暂停、批准、拒绝、连续确认和幂等。
- 多通道请求、审计查询和敏感字段脱敏。

常规验证命令为：

```bash
python -m pytest -q
git diff --check
```

本项目不实现生产级认证、租户隔离、密钥托管、完整 SSRF 防护、跨进程恢复和分布式并发控制。新增功能时应优先保持教学主线清晰，不为尚未出现的需求增加平台化抽象。

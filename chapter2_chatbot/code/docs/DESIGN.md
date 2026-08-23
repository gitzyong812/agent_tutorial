# 通用数字员工框架网页 MVP：基础 ChatBot 数字员工

## 1. 项目定位

本项目是《动手智能体构建》第 2 章的配套实践代码，构建一个通用的数字员工框架网页 MVP（最小可用系统），当前支持基础 ChatBot 类型的数字员工。

本章只实现三项核心能力，与正文一一对应：

- **模型调用参数**：决定用哪个模型、以怎样的方式生成回答；
- **系统提示词**：规定数字员工的身份与工作边界；
- **短期对话历史**：把已经发生的交流再次提供给模型，实现多轮连续对话。

RAG、工具调用、长期记忆、多 Agent 编排、账号登录和真实人工流转均不在首版范围内，留待后续章节扩展。

在实现上，系统功能与具体保险业务**解耦**：这是一个通用数字员工框架，通过配置（主要是提示词与参数）适配不同场景。首版演示场景为保险销售，面向保险公司内部人员作为用户，辅助其进行保险产品销售。用户可以创建不同角色的 ChatBot 形式数字员工（如高情商话术改写、政策专家），辅助销售保险产品。

> 设计原则：遵循 `AGENTS.override.md`，提供**最小可运行系统**，代码简洁、可读、有必要的中文注释，避免冗余设计与不必要的复杂性。

## 2. 前端页面

前端为单页应用（无前端框架），左侧是导航栏，包含多个 Tab，点击切换到不同功能页面。当前导航栏支撑三个功能页面：

1. **对话页面（默认展示）**：用户选择一个**已发布**的数字员工进行对话。支持流式（SSE）显示模型输出、连续发送消息、清空当前会话。左侧保存历史会话列表，支持新建会话、切换会话、删除会话。新建会话时可选择回答语言。
2. **模型配置**：默认展示已配置模型列表，支持创建、编辑、删除、启停模型配置。每项配置包含名称、供应商标识、`LLM_BASE_URL`、模型名和 API Key。
3. **数字员工配置**：默认展示数字员工列表，支持创建、编辑、删除基础 ChatBot 类型的数字员工（后续可扩展 RAG、Agent 等类型），并设置**草稿 / 已发布**状态。只有已发布的数字员工才能在对话页被选用。

数字员工配置必须与本章理论术语对应：

- **提示词要素**：角色（role）、任务目标（service_goal）、业务资料（business_context）、约束条件（constraints）、输出要求（output_instruction）。其中**参考样例（few-shot）并入业务资料字段填写**，不单独建字段，以保持配置精简。
- **模型调用参数**：`temperature`、`top_p`、`max_tokens`、`frequency_penalty`、`presence_penalty`。
- **多轮对话**：`history_turns`，保留最近若干轮完整问答。

## 3. 安全与业务边界

- 模型 API Key 首版**简单实现：明文存储于 SQLite 的普通文本字段，可直接编辑**。这样降低初学门槛；后续章节再引入加密与密钥管理。
- 系统提示词必须要求模型依据已配置资料回答；资料不足时明确说明无法确认，并建议人工核实，不得编造。
- 首版只生成文本，不调用外部系统，不保存长期记忆。
- 注意：明文存储仅适合本地学习演示，不应用于生产；切勿把含真实密钥的数据库文件提交到代码仓库（`.gitignore` 已忽略 `*.db`）。

## 4. 技术方案

- **后端**：Python、FastAPI、Pydantic、SQLAlchemy、Uvicorn。
- **模型调用**：`openai` Python SDK，使用 OpenAI 兼容接口，可连接 OpenAI、DeepSeek、Qwen 等服务（复用第 1 章的调用方式）。
- **数据库**：SQLite；后续章节可通过 `APP_DATABASE_URL` 切换到服务器数据库。
- **前端**：HTML、CSS、原生 JavaScript，不使用 Node.js、React 或 Vue，风格简约大气。
- **国际化**：`app/static/locales/zh.json` 与 `en.json`，界面文案尽量全部可配置；模型默认按用户输入语言回答。
- **流式输出**：消息接口返回 SSE，前端通过 `fetch` 读取流。

## 5. 数据模型

系统使用四类数据实体（SQLAlchemy ORM）。所有表在应用启动时自动建表。

### 5.1 `ModelConfig`（模型服务连接信息）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | int, PK | 主键 |
| `name` | str | 配置名称 |
| `provider` | str | 供应商标识（如 `openai`、`deepseek`、`qwen`） |
| `base_url` | str | OpenAI 兼容的 `LLM_BASE_URL` |
| `model_name` | str | 模型名（如 `deepseek-chat`） |
| `api_key` | str | API Key，**明文存储、可编辑**的普通文本字段 |
| `is_active` | bool | 启停状态，停用后不可被数字员工选用 |
| `created_at` / `updated_at` | datetime | 时间戳 |

### 5.2 `AgentConfig`（基础 ChatBot 配置）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | int, PK | 主键 |
| `name` | str | 数字员工名称 |
| `agent_type` | str | 首版固定 `chatbot`，保留字段供后续扩展 |
| `model_config_id` | int, FK | 关联使用的模型配置 |
| `role` | text | 角色定义（岗位、服务对象、工作范围、沟通风格） |
| `service_goal` | text | 任务目标 |
| `business_context` | text | 业务资料（可在其中写入参考样例 few-shot） |
| `constraints` | text | 约束条件（边界与禁止行为） |
| `output_instruction` | text | 输出要求 |
| `temperature` | float | 默认 0.2 |
| `top_p` | float | 默认 1.0 |
| `max_tokens` | int | 默认 500 |
| `frequency_penalty` | float | 默认 0 |
| `presence_penalty` | float | 默认 0 |
| `history_turns` | int | 保留最近多少轮完整问答，默认 5 |
| `status` | str | `draft` / `published`，仅 `published` 可被对话页使用 |
| `extensions` | JSON | 受控扩展位，保留 `future_capabilities` 字段 |
| `created_at` / `updated_at` | datetime | 时间戳 |

### 5.3 `ConversationSession`（会话）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | int, PK | 主键 |
| `title` | str | 会话标题（默认取首条用户消息摘要，可为空） |
| `agent_config_id` | int, FK | 本会话所选数字员工 |
| `language` | str | 回答语言：`zh` / `en` |
| `created_at` / `updated_at` | datetime | 时间戳 |

### 5.4 `ChatMessage`（短期对话记录）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | int, PK | 主键 |
| `session_id` | int, FK | 所属会话 |
| `role` | str | `user` / `assistant` |
| `content` | text | 消息内容 |
| `created_at` | datetime | 时间戳 |

> 扩展边界：`AgentConfig.agent_type` 首版固定为 `chatbot`，并保留受控的 `extensions.future_capabilities` 字段。后续章节可通过注册新的运行时类型扩展 `rag_chatbot`、`tool_agent`，但第 2 章**不建立**知识库、工具的数据表。

## 6. 后端接口（API）

所有业务接口以 `/api` 前缀提供，返回 JSON（流式消息接口除外）。

**模型配置**

- `GET /api/model-configs` —— 列表（含 `api_key` 明文，可直接编辑）
- `POST /api/model-configs` —— 创建
- `PUT /api/model-configs/{id}` —— 编辑
- `DELETE /api/model-configs/{id}` —— 删除
- `PATCH /api/model-configs/{id}/active` —— 启停

**数字员工配置**

- `GET /api/agents?status=published` —— 列表（可按状态过滤；对话页只取 `published`）
- `POST /api/agents` —— 创建
- `GET /api/agents/{id}` —— 详情
- `PUT /api/agents/{id}` —— 编辑
- `DELETE /api/agents/{id}` —— 删除
- `PATCH /api/agents/{id}/status` —— 设置草稿 / 已发布

**会话与消息**

- `GET /api/conversations` —— 历史会话列表
- `POST /api/conversations` —— 新建会话（选定数字员工、语言）
- `GET /api/conversations/{id}/messages` —— 拉取某会话的历史消息
- `DELETE /api/conversations/{id}` —— 删除会话（级联删除消息）
- `POST /api/conversations/{id}/messages` —— 发送用户消息，**返回 SSE 流**，逐块推送助手回答；流结束后持久化用户消息与完整助手回答

**核心调用逻辑**（与正文代码片段对应）：

```python
# 组装消息：系统提示词 + 最近 history_turns 轮 + 本轮输入
previous = existing[-(agent.history_turns * 2):]
messages = [
    {"role": "system", "content": build_system_prompt(agent)},
    *[{"role": item.role, "content": item.content} for item in previous],
    {"role": "user", "content": user_input},
]
```

`build_system_prompt` 按“角色 / 任务目标 / 业务资料 / 约束条件 / 输出要求”拼接系统提示词，并注入语言要求；要求模型仅依据业务资料回答，资料不足时说明无法确认并建议人工核实。

## 7. 目录约定

```
code/
├── .env.example            # 环境变量样例（APP_DATABASE_URL，可选）
├── .gitignore              # 忽略 .env、*.db、__pycache__ 等
├── requirements.txt        # fastapi / uvicorn / sqlalchemy / pydantic / openai / python-dotenv
├── README.md               # 运行说明与验收清单
└── app/
    ├── __init__.py
    ├── main.py             # FastAPI 入口：挂载路由与静态文件，启动时建表 + seed
    ├── config.py           # 读取 .env（APP_DATABASE_URL）
    ├── database.py         # SQLAlchemy engine / SessionLocal / Base / get_db
    ├── models.py           # ORM 模型：ModelConfig / AgentConfig / ConversationSession / ChatMessage
    ├── schemas.py          # Pydantic 请求/响应模型
    ├── llm.py              # OpenAI 兼容客户端、build_system_prompt、流式调用封装
    ├── seed.py             # 预置演示数据
    ├── routers/
    │   ├── __init__.py
    │   ├── model_configs.py
    │   ├── agents.py
    │   └── chat.py         # 会话 CRUD + SSE 消息
    └── static/
        ├── index.html      # 单页：左侧导航 + 三个功能页面容器
        ├── css/
        │   └── style.css
        ├── js/
        │   ├── app.js      # 导航切换、i18n 加载、通用 fetch 封装
        │   ├── chat.js     # 对话页（会话列表、流式渲染）
        │   ├── models.js   # 模型配置页
        │   └── agents.js   # 数字员工配置页
        └── locales/
            ├── zh.json
            └── en.json
```

## 8. 预置演示数据（seed）

应用首次启动（数据库为空）时自动写入演示数据，便于克隆后快速跑通验收流程：

1. **一个模型配置占位**：名称如“示例模型（请填写 API Key）”，`provider`/`base_url`/`model_name` 给出 DeepSeek 或 Qwen 的兼容示例值，`api_key` 留空、`is_active=false`，提示用户编辑后填入真实密钥并启用。
2. **1~2 个保险场景数字员工草稿**：如“高情商话术改写助手”“保险政策咨询专家”，预填 role / service_goal / business_context（含 1~2 条 few-shot 样例）/ constraints / output_instruction 与默认参数，状态为 `draft`，关联上面的示例模型配置。用户填好密钥后即可发布并对话。

> seed 仅在空库时执行一次，不覆盖用户已有数据。

## 9. 运行与验收

复制 `.env.example` 为 `.env`（如需自定义数据库），安装依赖后启动：

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

完成下列流程即可验收：

1. 编辑预置模型配置，填入真实 API Key 并启用。
2. 创建（或基于预置草稿）并发布话术改写数字员工。
3. 在对话页选择该数字员工，新建会话并完成三轮对话。
4. 检查模型能保持角色与上下文；资料不足时不会编造，且主动建议人工确认。
5. 新建、切换、删除多个历史会话，验证会话相互独立。
6. 切换中英文界面，验证文案与模型回答语言。

## 10. 与后续章节的能力边界

当前 ChatBot 仅依赖配置好的静态资料与短期对话历史。第 3 章加入知识检索（RAG），第 4 章加入工具调用与长期记忆，第 6 章再讨论多智能体编排与人工确认节点。本章保留 `agent_type` 与 `extensions` 字段，使后续扩展无需重写对话主流程。

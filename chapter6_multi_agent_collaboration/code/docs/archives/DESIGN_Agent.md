# 第 4 章增量设计：配备工具和记忆的 Agent 数字员工

本文档说明第 4 章相对 ChatBot 和 RAG 数字员工增加的 Agent 设计。项目整体架构见 [DESIGN.md](DESIGN.md)，教程正文见[第 4 章：配备工具和记忆的 Agent 数字员工](../../chapter4_agent_memory_tools.tex)。

本项目是本地教学 MVP，不是生产系统。实现参考了 [CowAgent](../../../../ref-projects/CowAgent) 的工具注册、循环执行和记忆生命周期思想，但没有复制它的渠道、工作空间、技能、MCP、后台调度和自主进化模块。

## 1. 教学目标与能力边界

本章新增 `react_agent` 类型，用一个可以观察和调试的最小系统展示以下闭环。

1. 模型根据目标决定直接回答、生成计划或调用工具。
2. 程序校验参数并执行真实工具。
3. 工具结果作为观察信息回填给模型。
4. Agent 根据新观察继续调用工具或生成最终回答。
5. 任务完成后，系统自动提取值得跨会话保存的日级记忆。
6. 用户在记忆页手工触发整理，将日级记忆沉淀为核心记忆。
7. 后续任务由 Agent 通过 `memory_search` 按需检索相关记忆。

本章不实现用户体系、权限审批、定时记忆巩固、Deep Dream、MCP、技能、任意 Python 或 Shell 工具。自定义 HTTP 工具和明文请求头只用于受信任的本地课堂环境。

## 2. ReActAgent 运行骨架

### 2.1 类型与配置

`AgentConfig.agent_type="react_agent"` 表示工具和记忆智能体。新增配置如下。

| 字段 | 默认值 | 作用 |
| --- | --- | --- |
| `tool_bindings` | `[]` | 通过关联表绑定 ToolConfig，并保存该 Agent 的工具超参数 |
| `max_steps` | `24` | 一次任务允许的最大工具调用轮数，范围 1 至 100。一轮可包含多个工具调用 |
| `memory_enabled` | `true` | 最终回答保存后是否自动提取日级记忆 |

新建 ReActAgent 默认绑定 `memory_search` 和 `calculator`，`plan` 是普通可选工具。`knowledge_search` 的知识标签、检索数量和检索方式保存在绑定记录的 `extra` 中。

### 2.2 一次任务的执行流程

核心运行时位于 `app/runners/react.py`。

```text
用户目标
  ↓
系统提示词 + 最近对话历史 + 工具 Schema
  ↓
OpenAI 兼容 Tool Calling
  ├─ 没有 tool_calls → 最终回答
  └─ 包含 tool_calls
       ↓
     记录模型明确返回的思考文本（如有）
       ↓
     参数解析与 JSON Schema 校验
       ↓
     执行工具并产生观察
       ↓
     assistant(tool_calls) + tool(tool_call_id) 回填
       ↓
     进入下一轮模型调用
```

系统使用原生 `tools`、`tool_choice="auto"` 和 `tool_calls` 协议，不增加提示词 JSON 降级。模型必须支持 OpenAI 兼容 Tool Calling。

每个工具结果都使用原调用的 `tool_call_id` 回填。工具参数错误、未知工具、HTTP 超时和执行异常会转换成 `{"ok": false, "result": {"error": "..."}}`，让模型根据错误继续处理，而不是直接终止任务。

达到 `max_steps` 后，系统停止提供工具，并要求模型根据已有观察总结结果及未完成部分。

### 2.3 SSE 事件与持久化

Agent 仍复用 `POST /api/conversations/{id}/messages`。新增两类 SSE 事件。

```text
event: trace
data: {"type":"thought","step":1,"content":"先查询等待期，再进行换算。"}

event: trace
data: {"type":"tool_call","step":1,"tool":"calculator","arguments":{...}}

event: trace
data: {"type":"tool_result","step":1,"tool":"calculator","result":{...}}
```

思考事件只记录模型明确返回的文本，内容为空时不生成。工具调用轮合并 `reasoning_content` 和 `content`；最终回答轮只记录 `reasoning_content`，避免把最终 `content` 重复展示为思考。所有工具采用统一事件，`plan` 也使用 `tool_call` 和 `tool_result`。工具失败使用 `type="tool_error"`。

最终回答仍通过 SSE `data` 返回。完整轨迹保存到 `ChatMessage.extra.agent_trace`，执行状态保存到 `extra.execution_status`，知识检索结果继续保存到 `extra.rag_sources`，刷新页面后都能恢复。执行中途失败时会保存失败轨迹，但不会触发长期记忆提取。

轨迹是单次 ReAct 输出的展示元数据，不作为独立消息写入对话历史。下一轮上下文只读取用户消息和最终回答，不会带入上一轮的思考、工具调用或工具结果。单次执行内部仍需临时回填 `assistant(tool_calls)` 和 `tool(tool_call_id)`，以满足 Tool Calling 协议并完成当前任务。

## 3. 工具机制

### 3.1 统一工具结构

`app/tools/registry.py` 统一管理工具的稳定 key、名称、说明、参数 JSON Schema 和执行逻辑。传给模型的结构为：

```json
{
  "type": "function",
  "function": {
    "name": "calculator",
    "description": "精确计算算术表达式",
    "parameters": {
      "type": "object",
      "properties": {
        "expression": {"type": "string"}
      },
      "required": ["expression"]
    }
  }
}
```

### 3.2 预设工具

| 工具 | 作用 | 关键边界 |
| --- | --- | --- |
| `plan` | 调用当前 Agent 的模型，把复杂任务拆解为详细执行计划 | 可选，仅在多步骤依赖或多工具协作任务中调用，不执行外部动作 |
| `calculator` | 精确计算算术表达式 | 使用受限 AST，不使用 `eval`，拒绝函数调用和属性访问 |
| `knowledge_search` | 检索当前 Agent 绑定的知识资料 | 复用第 3 章检索器，结果同时进入轨迹和引用资料区 |
| `memory_search` | 检索全局记忆和当前 Agent 记忆 | 返回相关片段，不把全部记忆塞入上下文 |

预设工具与 HTTP 工具都保存在 `ToolConfig` 中。预设工具的执行函数仍由代码实现，工具管理页只读展示，不能编辑或删除。

`plan` 的输入是需要完成的完整任务。它不会要求主 ReAct 模型预先生成步骤，而是内部发起一次不带工具的大模型调用，返回结构化计划。每个步骤包含具体动作、建议使用的已绑定工具和可检验的预期结果。简单问答、单次检索和单次计算不应调用 `plan`。计划结果作为观察信息回填主 ReAct 循环，首版不维护步骤状态，也不自动调度其他工具。

### 3.3 自定义 HTTP 工具

`ToolConfig` 保存全部可用工具，`tool_type` 用于区分 `builtin` 和 `http`。HTTP 工具使用以下专属字段。

| 字段 | 说明 |
| --- | --- |
| `name` | 模型可见的工具名，全局唯一，不能与预设工具重名 |
| `description` | 使用时机和能力边界 |
| `parameters_schema` | 顶层为 object 的 Draft 7 JSON Schema |
| `method` | `GET` 或 `POST` |
| `url` | HTTP 或 HTTPS 地址 |
| `headers` | 静态请求头，明文保存 |
| `is_enabled` | 是否允许运行时加载 |

运行规则固定如下。

- 创建和编辑时检查 Schema，调用时校验模型参数。
- GET 参数进入查询字符串，POST 参数进入 JSON 请求体。
- 超时为 10 秒，不自动跟随重定向。
- 最多保留 16 KB 响应。JSON 响应保持结构，其他响应按文本返回。
- 不支持动态 Python、网页脚本、Shell 命令和任意代码执行。

工具接口：

- `GET /api/tools`
- `POST /api/tools`
- `PUT /api/tools/{tool_id}`
- `DELETE /api/tools/{tool_id}`

`ReActAgentTool` 建立 ReActAgent 与 ToolConfig 的多对多关系，`extra` 保存知识标签、检索数量等绑定超参数。删除自定义工具时，其绑定记录同步删除。

## 4. 记忆机制

### 4.1 三层结构

本项目用已有消息和一个 SQLite 表表达三层记忆。

| 层级 | 实现 | 生命周期 |
| --- | --- | --- |
| 工作记忆 | `ChatMessage` 和 `history_turns` | 当前会话和最近若干轮 |
| 日级记忆 | `MemoryItem.layer="daily"` | 自动从完成的任务中提取 |
| 核心记忆 | `MemoryItem.layer="core"` | 由用户手工触发巩固 |

`MemoryItem` 的主要字段包括 `layer`、`scope`、`category`、`agent_config_id`、`content`、来源消息、日期、巩固状态和可选 embedding。

删除历史会话时，已经形成的长期记忆会保留，但来源会话和消息 id 会被清空。仍有历史会话或专属长期记忆的数字员工不能直接删除，避免产生悬空数据。

范围分为两级：

- `global`：用户通用偏好和稳定事实，所有 Agent 可以检索。
- `agent`：特定数字员工积累的任务经验，只能由该 Agent 检索。

类别分为 `fact` 和 `experience`。记忆与知识库保持分离，业务条款等外部事实仍由知识库负责。

### 4.2 自动形成日级记忆

仅 ReActAgent 在成功保存最终回答后执行自动提取。输入包括本轮用户消息、最终回答和工具轨迹。提取提示词要求模型只保存：

- 稳定用户偏好；
- 重要事实或决策；
- 已完成任务的关键结论；
- 可以在未来复用的执行经验。

寒暄、临时要求、模型推测和知识库原文不保存。模型返回最多 5 条结构化记忆。相同范围内相似度较高的内容会去重。提取或 embedding 失败不会影响已经生成和保存的回答。

### 4.3 手工巩固核心记忆

记忆页的“整理记忆”按全局或指定 Agent 读取尚未巩固的日级记忆，同时提供当前核心记忆。模型只能返回三种受控动作：

- `create`：创建新的核心记忆；
- `update`：更新当前范围内已有核心记忆；
- `delete`：删除当前范围内冲突或过时的核心记忆。

系统校验动作和目标 id，并在一个事务中应用。成功后将参与整理的日级记忆标记为已巩固，但不删除，以便观察来源。非法动作会整体回滚。

### 4.4 混合检索

`memory_search` 只加载全局和当前 Agent 范围的候选记忆。

- embedding 可用时，按 `0.7 × 向量相似度 + 0.3 × 关键词得分` 排序。
- embedding 缺失或调用失败时，自动使用关键词检索。
- 核心记忆不衰减。
- 日级记忆按 `1 / (1 + 天数 / 30)` 做简单时间衰减。
- 返回内容、层级、范围、类别、日期和得分。

记忆管理接口：

- `GET /api/memories`
- `POST /api/memories`
- `PUT /api/memories/{memory_id}`
- `DELETE /api/memories/{memory_id}`
- `POST /api/memories/consolidate`

## 5. 前端与种子数据

左侧导航新增“工具管理”和“记忆管理”。

- 工具页展示预设工具，并维护自定义 HTTP 工具。
- 记忆页按层级、范围和 Agent 筛选，支持手工增删改与记忆巩固。
- 数字员工页新增 ReActAgent 类型、列表式工具绑定、工具配置弹窗、最大步骤和记忆形成开关。
- 聊天页用折叠区展示执行轨迹，并复用 RAG 引用资料区展示知识检索结果。

空数据库首次启动会新增“保险业务助手”草稿，默认绑定 `calculator` 和 `memory_search`。`plan` 和 `knowledge_search` 可在列表中按需添加。

## 6. 测试与验收

自动测试位于 `tests/`，运行命令：

```bash
python -m pytest -q
```

测试覆盖：

- 计算器安全边界和工具参数校验；
- HTTP 工具请求映射；
- Tool Calling 消息顺序和 `tool_call_id`；
- 最大步骤终止；
- 记忆范围隔离、提取去重、巩固更新；
- 工具与记忆 API；
- SSE 轨迹和历史消息持久化。

建议课堂验收任务：让 Agent 先制定计划，再查询示例保险产品等待期，并用计算器完成一次相关计算。随后告诉 Agent 一个稳定偏好，新建会话后检查它能否通过 `memory_search` 找回。最后在记忆页触发整理，观察日级记忆如何沉淀为核心记忆。

## 7. 运行限制

- 不引入数据库迁移框架。第 3 章数据通过 `migrate_chapter3_db.py` 导入，旧版第 4 章工具绑定通过一次性 `migrate_tool_bindings.py` 转换。
- 对话模型必须支持 OpenAI 兼容的原生 Tool Calling。
- 模型 API Key、自定义 HTTP 请求头均明文保存，只适合本地学习。
- HTTP 工具没有生产级 SSRF 防护、密钥托管、权限审批和审计能力。
- 自动记忆提取会在每轮 Agent 回答后增加一次模型调用。
- 本项目没有后台任务，核心记忆只在用户点击“整理记忆”时更新。

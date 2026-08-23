# 第五章 Harness 功能设计

本章在原 ReAct 工具循环上增加可恢复状态、统一通道协议、必要的人工协同和程序化权限检查。实现保持教学规模，不加入账号认证、消息队列、监控基础设施或生产级断点恢复。

## 1. 总体结构

```text
网页 / CLI / 微信
    |
    v
StandardRequest -> harness/service.py -> 结构化事件 -> JSON SSE / 微信文本
                          |
                          v
                    ReactRunner 状态机
                    /       |       \
               Skills   ToolPolicy   HumanRequest
                                      ApprovalRequest
```

ChatBot、RAG 和 ReActAgent 共用结构化事件执行器。网页兼容入口补充 `channel=web` 和 `sender_id`，CLI 直接调用 `/api/harness/messages`，二者再序列化为 SSE。微信工作线程使用绑定的 `session_id` 创建 `channel=weixin` 请求，并把最终文本回复给消息发送者。`sender_id` 只用于通道和审计标记，不代表可信身份。

微信绑定保存在 `conversation_channel_bindings`。每个会话最多有一个微信绑定，独立保存凭证、长轮询游标和用户 `context_token`。应用启动时恢复已连接绑定，解绑或删除会话时停止对应工作线程。微信请求不暴露 `ask_human` 和写操作工具，但仍可以使用读取类工具及终止式 `handoff_to_human`。

## 2. 统一流式输出

每个 SSE 数据块都是一行 JSON：

```json
{
  "type": "text_delta | sources | trace | human_required | handoff | error | done",
  "run_id": 1,
  "payload": {}
}
```

`done.payload.status` 为 `completed`、`pending`、`handoff` 或 `failed`。生成器在 `finally` 中保存用户消息、助手消息、引用、轨迹和人工请求。客户端提前断开时，尚未进入可恢复状态的运行标记为失败，不留下无消息的 `running` 记录。

ReActAgent 的工具决策调用不会直接展示中间文本。模型生成最终回答时，运行器实时转发文本增量；运行器自身生成的提示文本按照 `REACT_TEXT_DELTA_CHARS` 分片。所有新建数字员工的默认最大输出长度由 `DEFAULT_AGENT_MAX_TOKENS` 控制，默认值为 `2048`。

## 3. ReAct 循环内人工输入

`ask_human(question, input_type)` 是默认绑定但可解除的内置工具。它用于缺少不可推断的关键信息，也允许在用户明确愿意讨论且聚焦问题会实质影响结果时使用。默认每轮最多调用两次，不能替代程序触发的工具授权。

调用过程如下：

1. 校验工具仍绑定，并校验 `input_type` 为 `confirm` 或 `text`。
2. 创建 `HumanRequest`，保存原 `tool_call_id`，将 `HarnessRun` 标记为 `pending`。
3. 发送 `human_required`，网页在当前助手消息中显示按钮或文本框，CLI 使用终端输入。
4. 回答接口通过条件更新原子领取请求。重复回答返回 `409`。
5. 回答作为原工具结果回填，从当前 `call_index` 继续。

同一 assistant 消息中可以连续包含多个人工请求，但总数受 `MAX_HUMAN_REQUESTS_PER_RUN` 限制。状态机仍按调用顺序每次只展示一个问题。消息的 `extra.human_request` 保存当前卡片，刷新页面后可以恢复。

## 4. 结构化转人工

`handoff_to_human(summary, missing_information, requested_action)` 同样默认绑定且可解除。Runner 校验参数后立即把运行标记为 `handoff`，保存结构化交接信息，发送 `handoff` 和说明文本，不再调用模型。

handoff 已结束本轮，因此普通输入框保持可用。用户补充信息时会创建新的 `HarnessRun`，原运行记录不恢复。

## 5. 工具权限

`ToolPolicy` 使用三种等级：

| 等级 | 行为 |
| --- | --- |
| `read` | 参数校验通过后自动执行 |
| `write` | 创建 `ApprovalRequest` 并暂停当前循环 |
| `restricted` | 拒绝执行并回填限制原因 |

写工具授权也使用 `human_required`，其中 `kind=tool_approval`。网页在当前消息中展示脱敏参数和批准、拒绝按钮，不跳转页面。拒绝结果作为原工具观察回填，模型可以给出替代方案。

暂停时，`HarnessRun.state` 保存工具配置指纹。批准后重新读取工具绑定、风险策略、参数 Schema、URL、Method 和请求头。任一项变化都会使旧授权失效。决定接口原子领取请求，重复决定返回 `409`。

## 6. 默认绑定

启动 seed 使用 `human_tools_default_applied` 标记。新建 ReActAgent 默认绑定 `ask_human` 和 `handoff_to_human`。已有 ReActAgent 只在首次升级时补齐一次。管理员解除绑定后，后续重启不会恢复。

未绑定的内置工具不会进入模型工具列表，也不能由名称绕过调用。

## 7. 系统监控

`GET /api/monitoring/overview` 支持按 `agent_config_id`、运行日期和事件日期筛选，并分别接收运行与事件页码。`page_size` 限制为 1 至 100，一次返回：

- `running`、`pending`、`completed`、`handoff`、`failed` 状态数量。
- 等待普通人工输入和等待工具授权的数量。
- 最近运行。
- 请求、技能激活、权限检查、人工请求、人工回答、工具完成、转人工和失败等关键事件。
- 两个列表各自的总数、页码和总页数。

事件数据在写入和返回时递归脱敏并截断。字段名包含密钥、令牌、密码、授权头或 secret 时不展示原值。监控页进入时加载数据，并只提供手工刷新。

## 8. 数据模型

| 表 | 作用 |
| --- | --- |
| `harness_runs` | 通道、状态和可恢复 ReAct 上下文 |
| `human_requests` | `ask_human` 的问题、回答和领取状态 |
| `approval_requests` | 高风险工具授权及执行结果 |
| `audit_events` | 脱敏后的关键运行事件 |
| `conversation_channel_bindings` | 会话级微信状态、凭证和轮询状态 |

SQLite 连接启用 `PRAGMA foreign_keys=ON`。删除会话时，运行、人工请求、授权和事件通过外键级联删除。

## 9. 旧工单清理

`scripts/migrate_remove_service_tickets.py` 在修改前备份数据库。它删除旧 `service_tickets` 表，仅删除 `tool_type=builtin` 的 `create_service_ticket` 及其绑定和策略，并移除 `service-ticket` 技能绑定。同名自定义 HTTP 工具不会删除。

未完成的旧工单授权和对应运行标记为失败，可恢复状态及消息中的旧卡片被清除。迁移可重复执行，结束时执行外键检查，异常时恢复备份。

## 10. 测试重点

- 网页和 CLI 解析相同 JSON SSE，文本无需二次反斜杠转义。
- 微信二维码、扫码状态、会话隔离、文本收发和重启恢复正确。
- 微信请求不创建 `HumanRequest` 或 `ApprovalRequest`，网页权限行为不变。
- `ask_human` 覆盖确认、文本、连续请求、刷新恢复和重复回答。
- handoff 后模型不再调用，普通对话可以继续新运行。
- 工具授权覆盖批准、拒绝、重复决定和配置指纹变化。
- 断流后运行与消息保持一致。
- 监控统计、事件过滤、递归脱敏和 SQLite 外键级联正确。
- 清理迁移覆盖备份、重复执行、保留同名自定义工具和失败恢复。

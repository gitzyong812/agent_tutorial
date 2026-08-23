[中文](./README.md) | [English](./README-en.md)

# 第五章 Harness 教学系统

本项目在第四章 ReActAgent 基础上增加技能、多通道、循环内人工协同、工具权限和系统监控。教学通道包括网页、CLI 和会话级微信接入。

## 运行

```bash
cd chapter5_harness/code
cp .env.example .env
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

浏览器打开 `http://127.0.0.1:8000`。首次运行会创建 `chatbot.db` 和演示数据，需要在“模型配置”中填写可用的模型地址与密钥，并发布数字员工。

在网页中打开已有对话，点击右上角“接入通道”，展开“命令行”并复制页面生成的命令。例如：

```bash
python -m app.cli --session-id 3 --base-url http://127.0.0.1:8000
```

CLI 会接入该网页会话并调用 `POST /api/harness/messages`，继续使用已经选择的数字员工和对话上下文。网页与 CLI 消费同一种 JSON SSE：

```json
{
  "type": "text_delta",
  "run_id": 1,
  "payload": {"content": "回答片段"}
}
```

事件类型包括 `text_delta`、`sources`、`trace`、`human_required`、`handoff`、`error` 和 `done`。`done.payload.status` 只使用 `completed`、`pending`、`handoff`、`failed`。

新建数字员工的 `max_tokens` 默认值统一为 `2048`，可通过 `DEFAULT_AGENT_MAX_TOKENS` 调整。ReActAgent 实时转发模型生成的最终回答增量，网页与 CLI 使用同一种流式输出。运行器自身生成的提示文本按照 `REACT_TEXT_DELTA_CHARS` 分片。

## 微信通道

打开任意已有对话，点击右上角“接入通道”，使用微信扫描二维码即可把微信绑定到当前会话。每个绑定继续使用该会话已经选择的数字员工，多个会话的凭证、轮询游标和消息记录彼此隔离。

第一版只支持文本收发。微信请求不会调用 `ask_human`，也不会暴露需要授权的写操作工具。任务需要写操作时，数字员工会提示用户回网页完成。微信凭证保存在本地 SQLite 中，只适合本章的单进程教学部署。

二维码登录与消息协议参考 [CowAgent 微信通道](https://docs.cowagent.ai/channels/weixin)。相关超时和服务地址可以通过 `.env` 中的 `WEIXIN_*` 配置调整。

## 人工协同与权限

新建或首次升级的 ReActAgent 默认绑定两个可解除的内置工具：

- `ask_human(question, input_type)`：缺少不可推断的关键信息，或用户明确愿意讨论且聚焦问题会实质影响结果时，可以暂停当前循环。默认每轮最多调用两次，`input_type` 支持 `confirm` 和 `text`，上限可通过 `MAX_HUMAN_REQUESTS_PER_RUN` 调整。
- `handoff_to_human(summary, missing_information, requested_action)`：当前任务无法继续时结束本轮，并给出结构化交接信息。

工具策略分为三种：

- `read` 自动执行。
- `write` 在当前对话气泡内显示授权卡，批准或拒绝后继续同一个 ReAct 循环。
- `restricted` 直接拒绝，并把限制作为工具观察回填模型。

批准写操作时，系统会重新检查工具绑定、风险策略、参数 Schema、URL、Method 和请求头。配置变化后不能复用旧授权。

## 系统监控

“系统监控”页面手工加载 `GET /api/monitoring/overview`，顶部展示关键运行指标，下方切换最近运行和脱敏事件。两个列表按时间倒序分页，支持按数字员工和日期筛选。页面不轮询，也不提供审批列表或业务工单。

## 旧数据库迁移

旧版本数据库包含服务工单示例时，先执行：

```bash
python scripts/migrate_remove_service_tickets.py --database chatbot.db
```

脚本会先备份 SQLite，再删除 `service_tickets` 表、旧内置工具与技能绑定。未完成的旧授权会被标记为失败。脚本可重复执行，并保留同名的用户自定义 HTTP 工具。

## 测试

```bash
python -m pytest -q
git diff --check
```

详细设计见 [docs/DESIGN.md](docs/DESIGN.md) 和 [docs/DESIGN_Harness.md](docs/DESIGN_Harness.md)。

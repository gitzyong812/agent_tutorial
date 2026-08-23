[中文](./README.md) | [English](./README-en.md)

# 第六章多智能体协作教学系统

本项目在前五章数字员工系统基础上增加多智能体团队协作。多个数字员工可以共享团队消息、记忆和文本文件，同时保留各自的角色提示词、局部执行轨迹和工具权限。

## 运行

```bash
cd chapter6_multi_agent_collaboration/code
cp .env.example .env
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

浏览器打开 `http://127.0.0.1:8000`。首次运行会创建 `chatbot.db` 和演示数据，需要在“模型配置”中填写可用的模型地址与密钥，并发布数字员工。


脚本会复用数据库中已启用的对话模型，创建并发布事实核查员、渠道分析员、宣传文案员和内容审核员，同时写入团队成员、共享记忆和 `activity-brief.md`。重复执行不会重复创建同名实践数据，也可以通过 `--model-config-id` 指定模型。

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

## 多智能体团队协作

网页中的“团队协作”页面可以选择多个已发布的数字员工组成团队。发送普通消息时，任务规划器根据成员职责分配任务；使用 `@数字员工名` 可以指定执行角色。任务通过 `depends_on` 形成依赖图，系统按拓扑批次执行，同一批中的任务最多使用 6 个线程并行运行。

团队成员共享消息历史、团队记忆和 UTF-8 文本文件。每个数字员工仍使用自己的角色提示词、局部任务上下文和工具配置。下游任务只接收自身任务及其依赖任务的结果，网页任务卡会显示任务编号和 `depends_on`。ReActAgent 在团队会话中不开放写工具、`ask_human` 和技能创建，以免并行任务进入不可恢复的人工暂停状态。

动态规划默认复用团队成员绑定的可用模型，不需要额外配置。需要为任务规划单独指定模型时，可以使用以下环境变量覆盖默认选择：

```text
GROUP_TASK_PLANNER_MODE=llm
GROUP_TASK_PLANNER_BASE_URL=
GROUP_TASK_PLANNER_MODEL_NAME=
GROUP_TASK_PLANNER_API_KEY=
GROUP_TASK_PLANNER_MAX_TOKENS=1024
```

团队成员模型不可用、规划模型调用失败或返回无效任务时，系统自动回退到基于团队成员、`@` 提及和依赖关键词的规则规划。

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

[中文](./README.md) | [English](./README-en.md)

# 基础 ChatBot 数字员工

《动手智能体构建》第 2 章配套代码。一个最小可运行的通用数字员工框架网页系统，
当前支持基础 ChatBot 类型的数字员工。系统能力与具体业务解耦，通过配置（提示词与参数）适配不同场景，
首版演示场景为保险销售。

本章实现三项核心能力：**模型调用参数**、**系统提示词**、**短期对话历史**。

## 功能

- **对话页**：选择已发布的数字员工，新建 / 切换 / 删除会话，流式（SSE）显示模型回答。
- **模型配置**：创建、编辑、删除、启停模型服务连接（OpenAI 兼容接口）。
- **数字员工配置**：编辑提示词要素（角色 / 任务目标 / 业务资料 / 约束条件 / 输出要求）与
  模型调用参数（temperature、top_p、max_tokens、frequency_penalty、presence_penalty、history_turns），
  设置草稿 / 已发布状态。
- 中英文界面切换。

## 运行

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

打开 http://127.0.0.1:8000 。首次启动会自动建表并写入演示数据
（一个模型配置占位 + 两个保险场景数字员工草稿）。

如需自定义数据库，复制 `.env.example` 为 `.env` 修改 `APP_DATABASE_URL`。

## 验收流程

1. 在「模型配置」编辑预置占位，填入真实 API Key（OpenAI / DeepSeek / Qwen 等兼容服务）并启用。
2. 在「数字员工」基于预置草稿（或新建）发布一个数字员工。
3. 在「对话」选择该数字员工，新建会话并完成三轮对话，观察上下文是否连续。
4. 测试资料不足、收益承诺等边界问题，检查是否拒绝编造并建议人工确认。
5. 新建、切换、删除多个会话，验证相互独立。
6. 切换中英文界面。

## 说明

- API Key 首版**明文存储**于 SQLite，仅适合本地学习演示，请勿用于生产，也不要提交含真实密钥的 `*.db`。
- 仅生成文本，不调用外部系统、不保存长期记忆。RAG、工具、长期记忆、多 Agent 编排留待后续章节。

## 目录

```
app/
├── main.py            # 入口：建表 + seed + 挂载路由/静态文件
├── config.py          # 读取 .env
├── database.py        # SQLAlchemy 连接与会话
├── models.py          # ORM：ModelConfig / AgentConfig / ConversationSession / ChatMessage
├── schemas.py         # Pydantic 请求/响应模型
├── llm.py             # build_system_prompt + 流式调用
├── seed.py            # 演示数据
├── routers/           # model_configs / agents / chat(含 SSE)
└── static/            # 原生 HTML/CSS/JS 单页前端 + 中英文语言包
```

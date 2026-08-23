[中文](./README.md) | [English](./README-en.md)

# 动手智能体构建：从 AI 数字员工到一人公司

本项目是一套关于智能体构建与开发的开源教程，供感兴趣的读者自学使用。全书以 AI 数字员工为主线，通过八个循序递进的章节，介绍大模型调用、多轮对话、RAG、工具调用、记忆、Harness 工程、多智能体协作和应用构建。各章包含基础理论、实践步骤和配套代码，具备基本的 Python 阅读和运行能力即可开始学习。

本项目由本人开设的智能体课程整理而来。受个人能力和经验所限，内容难免存在疏漏。现将其开源，希望与大家共同学习、讨论和完善。

![教程内容设计与关联](./assets/content_design.png)

## 内容速览

全书按照“模型调用 → 对话 → 知识 → 行动 → 治理 → 协作 → 应用 → 拓展”的路线组织内容。

| 章节 | 主题 | 阶段成果 | 正文 | 配套代码 |
| --- | --- | --- | --- | --- |
| 第 1 章 | 大模型与智能体技术基础 | 完成开发环境准备和第一次大模型 API 调用 | [阅读](./chapter1_basics/README.md) | [代码](./chapter1_basics/code/) |
| 第 2 章 | 基础 ChatBot 数字员工 | 完成具有角色提示词和多轮上下文的数字员工 | [阅读](./chapter2_chatbot/README.md) | [代码](./chapter2_chatbot/code/) |
| 第 3 章 | 知识增强的 RAG 数字员工 | 完成能够依据外部资料回答问题的数字员工 | [阅读](./chapter3_rag/README.md) | [代码](./chapter3_rag/code/) |
| 第 4 章 | 配备工具和记忆的 Agent 数字员工 | 完成具备工具调用、ReAct 循环和长期记忆的智能体 | [阅读](./chapter4_agent_memory_tools/README.md) | [代码](./chapter4_agent_memory_tools/code/) |
| 第 5 章 | Harness 工程 | 完成可控、可靠、可追踪的智能体服务 | [阅读](./chapter5_harness/README.md) | [代码](./chapter5_harness/code/) |
| 第 6 章 | 多智能体协作系统 | 完成具有角色分工和任务依赖的智能体团队 | [阅读](./chapter6_multi_agent_collaboration/README.md) | [代码](./chapter6_multi_agent_collaboration/code/) |
| 第 7 章 | 智能体应用构建与一人公司 | 使用前述能力完成一人网店综合应用 | [阅读](./chapter7_opc_applications/README.md) | [代码](./chapter6_multi_agent_collaboration/code/) |
| 第 8 章 | 进阶与拓展 | 理解多模态、持续任务、开放框架与智能体平台 | [阅读](./chapter8_advanced/README.md) | 实践 |

## 如何使用本教程

建议按照章节顺序学习。运行代码前，请先阅读对应章节和该章的 `code/README.md`。各章的具体要求略有不同，通常可以按以下方式启动：

```bash
cd chapterN_xxx/code
cp .env.example .env
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

第 1 章为 Python 脚本，无需启动 Web 服务。具体操作以各章说明为准。

运行实验时，请在本地 `.env` 或系统环境变量中填写模型服务信息，不要提交真实 API Key、包含密钥的数据库或运行日志。

## 项目结构

```text
.
├── README.md                         # 教程首页与总目录
├── assets/                           # 全书公共图片
├── chapter1_basics/                  # 第 1 章正文、图片、PPT 和代码
├── chapter2_chatbot/                 # 第 2 章正文、图片和代码
├── chapter3_rag/                     # 第 3 章正文、图片和代码
├── chapter4_agent_memory_tools/      # 第 4 章正文、图片和代码
├── chapter5_harness/                 # 第 5 章正文、图片和代码
├── chapter6_multi_agent_collaboration/ # 第 6 章正文、图片和代码
├── chapter7_opc_applications/        # 第 7 章正文
└── chapter8_advanced/                # 第 8 章正文
```

## 交流与合作

欢迎通过 Issue 和 Pull Request 参与教程共建，包括：

- 报告错别字、失效链接和技术错误
- 改进不够清楚的概念解释或实践步骤
- 修复配套代码问题
- 补充测试案例、教学建议或实践素材
- 改进图片、表格和 Mermaid 图

提交修改前，请确保内容准确、代码能够运行。

如果你希望围绕本教程开展课程建设、教师培训、企业智能体咨询、教程出版、技术分享或项目共建，欢迎通过本仓库 Issue 联系作者。为了便于区分，请在标题中注明“合作交流”。

## 许可证

本项目采用 [Apache License 2.0](./LICENSE)。除第三方组件另有声明外，教程正文、原创图片和配套代码均按该许可证开放使用。

仓库中 DOMPurify、Marked 等第三方组件保留其原始许可证文件，使用时应同时遵守对应条款。

Copyright 2026 Yong Zhang

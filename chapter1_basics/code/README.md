[中文](./README.md) | [English](./README-en.md)

# 第 1 章配套代码

本目录包含《动手智能体构建》第 1 章的最小大模型调用示例。程序会分别执行一次普通问答和一次带角色提示词的问答，帮助读者观察系统提示词对回答方式的影响。

## 环境准备

建议使用 Python 3.10 或更高版本，并在虚拟环境中安装依赖：

```bash
python -m pip install -r requirements.txt
```

复制环境变量示例文件：

```bash
cp .env.example .env
```

根据所使用的 OpenAI 兼容模型服务填写 `.env`。不要提交包含真实 API Key 的 `.env` 文件。

## 运行

在本目录执行：

```bash
python main.py
```

如果配置正确，终端会依次输出普通提示词和角色提示词对应的模型回答。详细代码说明和实践要求请参见[第 1 章正文](../README.md)。

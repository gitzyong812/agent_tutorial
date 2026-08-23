[中文](./README.md) | [English](./README-en.md)

# Basic ChatBot Digital Employee

This is the companion code for Chapter 2 of *Hands-On Agent Building*. It is a minimal runnable web system that provides a general-purpose digital employee framework and currently supports basic ChatBot digital employees. System capabilities are separated from specific business domains, so prompts and parameters can adapt the system to different scenarios. The first version demonstrates an insurance sales scenario.

This chapter implements three core capabilities: **model call parameters**, **system prompts**, and **short-term conversation history**.

## Features

- **Chat**: Select a published digital employee; create, switch, and delete sessions; and display model responses as an SSE stream.
- **Model Configuration**: Create, edit, delete, enable, and disable model service connections through OpenAI-compatible interfaces.
- **Digital Employee Configuration**: Edit prompt elements, including the role, task objective, business information, constraints, and output requirements. Configure model call parameters, including temperature, top_p, max_tokens, frequency_penalty, presence_penalty, and history_turns, and set the status to draft or published.
- Switch between Chinese and English interfaces.

## Run

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. On first startup, the system automatically creates the database tables and inserts demonstration data consisting of one placeholder model configuration and two draft digital employees for insurance scenarios.

To use a custom database, copy `.env.example` to `.env` and modify `APP_DATABASE_URL`.

## Acceptance Procedure

1. Under Model Configuration, edit the preset placeholder, enter a real API key for an OpenAI-compatible service such as OpenAI, DeepSeek, or Qwen, and enable it.
2. Under Digital Employees, publish a digital employee based on a preset draft or create a new one.
3. Under Chat, select that digital employee, create a session, and conduct a three-turn conversation. Check whether the context remains continuous.
4. Test boundary questions involving insufficient information or promised returns. Check that the employee refuses to fabricate information and recommends human confirmation.
5. Create, switch, and delete multiple sessions to verify that they remain independent.
6. Switch between the Chinese and English interfaces.

## Notes

- In this first version, API keys are stored in **plaintext** in SQLite. This is suitable only for local learning demonstrations. Do not use it in production or commit a `*.db` file containing real credentials.
- The system generates text only. It does not call external systems or retain long-term memory. RAG, tools, long-term memory, and multi-agent orchestration are introduced in later chapters.

## Directory Structure

```
app/
├── main.py            # Entry point: create tables, seed data, and mount routes/static files
├── config.py          # Read .env
├── database.py        # SQLAlchemy connection and sessions
├── models.py          # ORM: ModelConfig / AgentConfig / ConversationSession / ChatMessage
├── schemas.py         # Pydantic request/response models
├── llm.py             # build_system_prompt + streaming calls
├── seed.py            # Demonstration data
├── routers/           # model_configs / agents / chat (including SSE)
└── static/            # Plain HTML/CSS/JS single-page frontend + Chinese/English language packs
```

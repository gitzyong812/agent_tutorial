[中文](./README.md) | [English](./README-en.md)

# Chapter 4: An Agent Digital Employee with Tools and Memory

This is the companion teaching project for Chapter 4 of *Hands-On Agent Building*. The system inherits the ChatBot and RAG digital employees from the previous two chapters and adds a ReActAgent that can create plans, call tools, observe results, and accumulate long-term memory.

## 1. Install and Run

Use Python 3.10 or later.

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` in a browser.

To import data from Chapter 3, run `python scripts/migrate_chapter3_db.py`. For an older Chapter 4 database, first run `python scripts/migrate_tool_bindings.py` to migrate tool bindings. Then run `python scripts/migrate_memories.py` to aggregate the previous daily memories into diaries while preserving core memories.

## 2. Pages

The sidebar contains six pages.

- Chat: Select a published ChatBot, RAG, or ReActAgent to complete tasks.
- Knowledge Base: Manage materials, chunks, and retrieval debugging.
- Tool Management: Inspect preset tools and create custom HTTP tools.
- Memory Management: Browse diaries and core memories with pagination, manually revise them, or consolidate memories.
- Model Configuration: Configure chat models that support OpenAI-compatible interfaces.
- Digital Employees: Configure and publish different types of digital employees.

## 3. Configure the Model and Knowledge Base

Open Model Configuration and enter the `base_url`, model name, and API key. ReActAgent uses native tool calling, so the selected model must support the OpenAI-compatible `tools` and `tool_calls` fields.

Vector retrieval for the knowledge base uses the embedding settings in `.env`:

```bash
EMBEDDING_BASE_URL=https://your-compatible-endpoint
EMBEDDING_MODEL_NAME=your-embedding-model
EMBEDDING_API_KEY=your-api-key
EMBEDDING_DIMENSIONS=
```

Without embedding, both knowledge retrieval and memory retrieval can fall back to keyword retrieval.

By default, core memories are consolidated automatically at 2:00 a.m. each day. The application also performs one catch-up run at startup. It automatically skips diaries that have already been consolidated and have not been updated since. You can adjust or disable this behavior through `.env`:

```bash
MEMORY_DREAM_ENABLED=true
MEMORY_DREAM_HOUR=2
```

## 4. Try ReActAgent

Open Digital Employees and edit the preset Insurance Business Assistant. The administrator represents the insurance staff member using the system, while the customer is the subject of the insurance needs. Do not confuse the two.

1. Select a configured chat model.
2. Confirm that the type is ReActAgent.
3. Add `knowledge_search` from the tool list as needed, then select insurance knowledge tags and retrieval parameters in the dialog.
4. Keep the default `calculator` and `memory_search` bindings.
5. Initially keep the default maximum number of tool-call rounds at 24. Ordinary tasks do not require a higher value. For complex teaching experiments, it can be adjusted from 1 to 100.
6. Enable Update Diary After Task as needed. This setting controls updates to the current day's diary. The `memory_search` tool controls the use of existing memories. The two are independent.
7. Save and publish the employee.

`plan` is an optional tool. Bind it for complex tasks that contain multiple dependent steps or require several types of tools to work together. It reuses the current agent's model to break the complete task into an execution plan containing concrete actions, suggested tools, and expected results.

Create a session under Chat and test the following:

```text
客户 C001 希望为一只 3 岁母猫购买为期 8 个月的短期宠物医疗险。
请检索可参考的保障、等待期和理赔资料，资料不足时明确说明，
再按给定的教学假设完成保费估算并形成产品设计草案。
```

A collapsible execution trace appears above the answer. It distinguishes model text, tool calls, and tool results as thinking, action, and observation. Chunks returned by knowledge retrieval still appear under Sources.

## 5. Configure an HTTP Tool

The `plan`, `calculator`, `knowledge_search`, and `memory_search` tools on the Tools page are read-only presets.

When creating an HTTP tool, enter:

- A tool name and clear capability description
- A parameter JSON Schema
- GET or POST
- An HTTP or HTTPS address
- Optional static request headers

GET parameters are placed in the query string, while POST parameters are sent as a JSON request body. Requests time out after 10 seconds, do not follow redirects, and retain at most 16 KB of the response.

Request headers and model API keys are stored in plaintext in SQLite. Do not store real credentials in a shared environment or code repository.

## 6. Observe the Memory Lifecycle

In a ReActAgent conversation, first provide customer requirements and staff preferences with a clearly identified subject. For example:

```text
客户 C001 的投保对象是 1 只 3 岁母猫，希望保障 8 个月左右。
我作为保险业务人员，希望产品草案先说明适用对象和保障范围，
再列出保费假设与风险提示。
```

After the task finishes, open Memory Management. The Diaries page should show the current day's global diary and the current ReActAgent diary. After every successful task, the system asynchronously updates both Markdown diaries for that day after sending the response. A failed diary update does not affect the normal answer. Check the backend logs to diagnose the model response format.

Create a new session and ask:

```text
客户 C001 再次咨询之前的宠物保险方案。
请说明已知需求，并列出下一步需要核实的产品信息。
```

When needed, the agent should call `memory_search` to retrieve global diaries and core memories as well as those visible to the current digital employee.

Each day, the system automatically reads unconsolidated diary increments and combines them with existing core memories to merge, update, or delete entries. You can also open Core Memories, select the global scope or a digital employee, and consolidate them manually. Diaries do not distinguish facts from experience. Core memories remain divided into factual information and task experience and are kept to a small, stable set where possible.

## 7. Automated Tests

```bash
python -m pytest -q
```

The tests do not call real models or external APIs. They use an isolated temporary SQLite database and simulated responses.

## 8. Suggested Acceptance Checklist

1. Existing ChatBot and RAG digital employees can still converse normally.
2. ReActAgent can call `plan`, `knowledge_search`, and `calculator`.
3. Invalid calculation expressions and HTTP failures are returned as observations, and the agent does not fabricate success.
4. Execution traces and sources remain after a refresh.
5. Consecutive tasks on the same day update only one global diary and one diary for the current agent.
6. Manual consolidation can create or update named, categorized core memories from diary increments.
7. Daily automatic consolidation processes only diaries that have not been consolidated or were updated afterward.
8. Custom HTTP tools can be created, bound, and called.

## 9. Teaching Boundaries

This project does not include accounts, permission approval workflows, external task queues, MCP, a skill system, or production-grade security controls. Daily memory consolidation uses an in-process scheduler and is intended for local teaching. Its purpose is to make the ReAct loop, tool protocol, and memory lifecycle visible to learners, not to build a general-purpose agent platform ready for production.

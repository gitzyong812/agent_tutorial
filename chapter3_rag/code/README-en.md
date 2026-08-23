[中文](./README.md) | [English](./README-en.md)

# Chapter 3 RAG Digital Employee Practice Project

This is the companion code for Chapter 3 of *Hands-On Agent Building*. You will run a local web system and build a RAG digital employee that searches a knowledge base and displays its sources.

In this chapter, you will complete three tasks:

1. Configure a chat model so the system can respond correctly.
2. Build a knowledge base and observe document chunking and retrieval results.
3. Publish a RAG digital employee and use conversations to verify that its answers come from the provided materials.

## 1. Environment Setup

Python 3.10 or later is recommended. The `/usr/bin/python3` included with macOS may be Python 3.9, which can produce an error involving the `int | None` type annotation during startup.

Install the dependencies:

```bash
pip install -r requirements.txt
```

Start the project:

```bash
uvicorn app.main:app --reload
```

Open the following address in a browser:

```text
http://127.0.0.1:8000
```

On first startup, the system automatically creates `chatbot.db` and inserts a demonstration model, digital employee, tags, and knowledge documents.

## 2. Pages

The sidebar contains four pages:

- Chat: Chat with a published digital employee.
- Knowledge Base: Manage tags, documents, chunks, and retrieval debugging.
- Model Configuration: Enter the endpoint, model name, and API key for the chat model.
- Digital Employees: Configure and publish ChatBot or RAG digital employees.

## 3. Step 1: Configure the Chat Model

Open Model Configuration and edit the preset example model.

Complete the following fields:

- `provider`: The provider name, such as `deepseek`, `openai`, or `qwen`.
- `base_url`: The OpenAI-compatible endpoint.
- `model_name`: The chat model name.
- `api_key`: Your API key.

Save the configuration and click Test. Continue only after the test succeeds.

Note: The API key is stored in plaintext in the local SQLite database. This project is intended only for local learning. Do not commit a database file that contains real credentials.

## 4. Step 2: Configure the Embedding Model

RAG vector retrieval requires an embedding model. This setting is not entered on the web page. Instead, create a `.env` file in this directory.

Example:

```bash
EMBEDDING_BASE_URL=https://your-compatible-endpoint
EMBEDDING_MODEL_NAME=your-embedding-model
EMBEDDING_API_KEY=your-api-key
EMBEDDING_DIMENSIONS=
```

You may initially leave `EMBEDDING_DIMENSIONS` empty. Restart uvicorn after modifying `.env`.

You can still complete the chapter exercises without an embedding model. The system automatically falls back to keyword retrieval, although you will not experience the full effect of vector retrieval.

## 5. Step 3: Build the Knowledge Base

Open the Knowledge Base page.

You can use the preset example documents or create your own.

Recommended procedure:

1. Click Manage Tags and create a tag, such as “Insurance Terms.”
2. Click New Document.
3. Enter the document name, source, and version.
4. Select the tag.
5. Paste Markdown or plain text.
6. Save the document.

The system automatically chunks and indexes the document after it is saved.

A document status of `indexed` means that both chunking and embedding succeeded.

A status of `failed` usually means that embedding was not configured or the model call failed. The text chunks can still be used for keyword retrieval.

After configuring embedding, click Rebuild Index to generate vectors for existing documents.

## 6. Step 4: Debug Retrieval

Click Retrieval Debugging on the Knowledge Base page.

Enter a question, for example:

```text
疾病责任等待期是多久？
```

Check whether the returned chunks are relevant to the question. Focus on three points:

- Whether the correct document was retrieved.
- Whether the correct chunk was retrieved.
- Whether changing `top_k` changes the returned chunks.

The quality of a RAG answer first depends on retrieving the correct material. Debug retrieval before testing conversations.

## 7. Step 5: Publish a RAG Digital Employee

Open Digital Employees and edit the preset Insurance Knowledge Q&A Assistant, or create a new digital employee.

Key settings:

- Select RAG Digital Employee as the type.
- Select an available chat model.
- Enter the role, task objective, constraints, and output requirements.
- Bind knowledge tags.
- Initially set `top_k` to 3.
- Initially select Vector as the retriever type. Select Keyword if embedding is unavailable.
- Save and then click Publish.

Do not place large amounts of business material directly in the prompt of a RAG digital employee. Business facts should reside in knowledge base documents and be supplied dynamically through retrieval.

## 8. Step 6: Validate Through Conversation

Open Chat, create a session, select the published RAG digital employee, and begin asking questions.

Test the following three types of questions.

### A Question Directly Answered by the Materials

```text
这个产品的疾病责任等待期是多久？
```

Expected result: The model states the waiting period and displays source material below the answer.

### A Question That Requires Multiple Chunks

```text
退保和理赔材料分别有哪些注意点？
```

Expected result: The model combines information from multiple chunks and displays multiple sources.

### A Question Not Answered by the Knowledge Base

```text
这个产品保证收益是多少？
```

Expected result: The model explains that the current materials are insufficient and recommends human verification instead of fabricating an answer.

## 9. Chapter Task Checklist

After running the project, complete at least the following tasks:

1. Configure and test a chat model.
2. Create a knowledge document and bind a tag to it.
3. Use Retrieval Debugging to inspect the matched chunks for at least three questions.
4. Publish a RAG digital employee.
5. Complete a conversation test and check whether sources appear below the answer.
6. Refresh the browser and confirm that sources for earlier answers remain available.
7. Adjust `top_k` or the retriever type and observe how the answer changes.

## 10. Frequently Asked Questions

### Startup Reports `unsupported operand type(s) for |`

This error is caused by an outdated Python version. Use Python 3.10 or later.

### The Document Status Is `failed`

Embedding is usually unconfigured or its call has failed. You can continue with keyword retrieval. After configuring `.env`, restart the service and click Rebuild Index.

### No Sources Appear During a Conversation

Check the following first:

- Whether the digital employee is a RAG type.
- Whether tags are bound to the digital employee.
- Whether those tags contain documents.
- Whether the documents have expired.
- Whether Retrieval Debugging can find relevant chunks.

### Do Sources Remain After a Refresh?

Yes. Sources for RAG answers are stored with the message records and remain visible after the page is refreshed.

### Can I Upload PDF or Word Files?

The current version supports only `.txt`, `.md`, and `.markdown`. PDF and Word parsing are left as future extensions.

## 11. Learning Focus

Do not judge the chapter only by whether the model's answers sound fluent. Examine the evidence behind each answer.

- Was the document chunked correctly?
- Did retrieval find the correct material?
- Is the answer grounded in its cited sources?
- Does the employee refuse to fabricate information when the materials are insufficient?

You understand the basic operation of a RAG digital employee only when you can connect all these stages.

from app import models
from app.runners.chatbot import ChatbotRunner
from app.runners.rag import RagRunner


def test_chatbot_runner_keeps_existing_message_shape(db, agent):
    agent.agent_type = "chatbot"
    history = [
        models.ChatMessage(session_id=1, role="user", content="上一问"),
        models.ChatMessage(session_id=1, role="assistant", content="上一答"),
    ]
    messages, sources = ChatbotRunner(db, agent).build_messages(history, "本轮问题")
    assert [message["role"] for message in messages] == ["system", "user", "assistant", "user"]
    assert messages[-1]["content"] == "本轮问题"
    assert sources == []


def test_rag_runner_still_returns_sources(db, agent, monkeypatch):
    agent.agent_type = "rag_chatbot"
    agent.knowledge_tag_ids = [1]
    passage = type(
        "PassageStub",
        (),
        {
            "document_id": 1,
            "document_name": "文档",
            "source_title": "等待期",
            "embedding_model_name": "",
            "content": "等待期为 90 天",
            "score": 1.0,
        },
    )()
    monkeypatch.setattr("app.runners.rag.build_rag_query", lambda *args, **kwargs: (True, "等待期"))
    monkeypatch.setattr("app.runners.rag.retriever.search", lambda *args, **kwargs: [passage])
    messages, sources = RagRunner(db, agent).build_messages([], "等待期多久")
    assert sources == [passage]
    assert "等待期为 90 天" in messages[0]["content"]

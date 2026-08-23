"""ORM 数据模型：模型配置、数字员工、会话与消息。"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.now()


class ModelConfig(Base):
    """模型服务连接信息。首版 API Key 明文存储，便于初学。"""

    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(50), default="openai")
    base_url: Mapped[str] = mapped_column(String(300))
    model_name: Mapped[str] = mapped_column(String(100))
    api_key: Mapped[str] = mapped_column(String(300), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class AgentConfig(Base):
    """基础 ChatBot 数字员工配置：提示词要素 + 模型调用参数。"""

    __tablename__ = "agent_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # 首版固定 chatbot，保留字段供后续扩展 rag_chatbot、tool_agent。
    agent_type: Mapped[str] = mapped_column(String(50), default="chatbot")
    model_config_id: Mapped[int] = mapped_column(ForeignKey("model_configs.id"))

    # 提示词要素
    role: Mapped[str] = mapped_column(Text, default="")
    service_goal: Mapped[str] = mapped_column(Text, default="")
    business_context: Mapped[str] = mapped_column(Text, default="")
    constraints: Mapped[str] = mapped_column(Text, default="")
    output_instruction: Mapped[str] = mapped_column(Text, default="")

    # 模型调用参数
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    top_p: Mapped[float] = mapped_column(Float, default=1.0)
    max_tokens: Mapped[int] = mapped_column(Integer, default=500)
    frequency_penalty: Mapped[float] = mapped_column(Float, default=0.0)
    presence_penalty: Mapped[float] = mapped_column(Float, default=0.0)

    history_turns: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft / published
    extensions: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    model: Mapped["ModelConfig"] = relationship()


class ConversationSession(Base):
    """一次连续对话会话。"""

    __tablename__ = "conversation_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    agent_config_id: Mapped[int] = mapped_column(ForeignKey("agent_configs.id"))
    language: Mapped[str] = mapped_column(String(10), default="zh")  # zh / en
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    agent: Mapped["AgentConfig"] = relationship()
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    """短期对话记录中的一条消息。"""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("conversation_sessions.id"))
    role: Mapped[str] = mapped_column(String(20))  # user / assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    session: Mapped["ConversationSession"] = relationship(back_populates="messages")

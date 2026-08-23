"""ORM 数据模型：数字员工、会话、知识库，以及第 4 章新增的工具和记忆。"""
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import DEFAULT_AGENT_MAX_STEPS, DEFAULT_AGENT_MAX_TOKENS
from .database import Base


def _now() -> datetime:
    return datetime.now()


# 文档与标签的多对多关联表：rag 数字员工通过一组标签圈定可用知识范围。
document_tags = Table(
    "document_tags",
    Base.metadata,
    Column("document_id", ForeignKey("knowledge_documents.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("knowledge_tags.id", ondelete="CASCADE"), primary_key=True),
)


class ModelConfig(Base):
    """模型服务连接信息。首版 API Key 明文存储，便于初学。"""

    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(50), default="openai")
    base_url: Mapped[str] = mapped_column(String(300))
    model_name: Mapped[str] = mapped_column(String(100))
    api_key: Mapped[str] = mapped_column(String(300), default="")
    # config_type 区分用途：chat 用于对话补全，embedding 用于向量化（指向 /embeddings 端点）。
    config_type: Mapped[str] = mapped_column(String(20), default="chat")
    # 仅 embedding 配置使用：向量维度，便于检索时对齐。
    dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class AgentConfig(Base):
    """数字员工配置：提示词要素 + 模型调用参数；第 3 章起支持 rag 类型。"""

    __tablename__ = "agent_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # chatbot：基础对话；rag_chatbot：检索增强；react_agent：工具与记忆智能体。
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
    max_tokens: Mapped[int] = mapped_column(Integer, default=DEFAULT_AGENT_MAX_TOKENS)
    frequency_penalty: Mapped[float] = mapped_column(Float, default=0.0)
    presence_penalty: Mapped[float] = mapped_column(Float, default=0.0)

    history_turns: Mapped[int] = mapped_column(Integer, default=5)

    # RAG 相关配置（仅 rag_chatbot 类型使用）
    # 绑定的标签 id 列表：检索范围 = 命中这些标签且未过期的文档的片段。
    knowledge_tag_ids: Mapped[list] = mapped_column(JSON, default=list)
    retrieval_top_k: Mapped[int] = mapped_column(Integer, default=3)
    retriever_type: Mapped[str] = mapped_column(String(20), default="vector")  # vector / keyword / hybrid

    # Agent 相关配置（仅 react_agent 类型使用）
    max_steps: Mapped[int] = mapped_column(Integer, default=DEFAULT_AGENT_MAX_STEPS)
    memory_enabled: Mapped[bool] = mapped_column(default=True)

    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft / published
    extensions: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    model: Mapped["ModelConfig"] = relationship()
    tool_bindings: Mapped[list["ReActAgentTool"]] = relationship(
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="ReActAgentTool.tool_config_id",
    )
    skill_bindings: Mapped[list["AgentSkillBinding"]] = relationship(
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="AgentSkillBinding.skill_name",
    )

    @property
    def skill_names(self) -> list[str]:
        return [item.skill_name for item in self.skill_bindings]


class ConversationSession(Base):
    """一次连续对话会话。"""

    __tablename__ = "conversation_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    agent_config_id: Mapped[int] = mapped_column(ForeignKey("agent_configs.id"))
    language: Mapped[str] = mapped_column(String(10), default="zh")  # zh / en / ru
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    agent: Mapped["AgentConfig"] = relationship()
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )
    channel_bindings: Mapped[list["ConversationChannelBinding"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class ConversationChannelBinding(Base):
    """外部消息通道与指定会话的一对一绑定。"""

    __tablename__ = "conversation_channel_bindings"
    __table_args__ = (
        UniqueConstraint("session_id", "channel_type", name="uq_session_channel"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("conversation_sessions.id", ondelete="CASCADE")
    )
    channel_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="waiting_scan")
    # credentials 只在服务端使用，不通过 API 返回。
    credentials: Mapped[dict] = mapped_column(JSON, default=dict)
    # state 保存二维码、长轮询游标和各微信用户的 context_token。
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    session: Mapped["ConversationSession"] = relationship(back_populates="channel_bindings")


class ChatMessage(Base):
    """短期对话记录中的一条消息。"""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("conversation_sessions.id"))
    role: Mapped[str] = mapped_column(String(20))  # user / assistant
    content: Mapped[str] = mapped_column(Text)
    # 附加消息元数据，例如 RAG 回答的引用资料 rag_sources。
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    session: Mapped["ConversationSession"] = relationship(back_populates="messages")


# ---------- 第 6 章新增：多智能体团队协作 ----------
class GroupConversation(Base):
    """多智能体团队会话，共享消息、记忆和文本文件。"""

    __tablename__ = "group_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="团队会话")
    language: Mapped[str] = mapped_column(String(10), default="zh")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    members: Mapped[list["GroupConversationMember"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="GroupConversationMember.id",
    )
    messages: Mapped[list["GroupChatMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="GroupChatMessage.id",
    )
    memories: Mapped[list["GroupMemory"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="GroupMemory.id",
    )
    files: Mapped[list["GroupFile"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="GroupFile.id",
    )


class GroupConversationMember(Base):
    """团队会话中的数字员工成员。"""

    __tablename__ = "group_conversation_members"
    __table_args__ = (
        UniqueConstraint("group_id", "agent_config_id", name="uq_group_agent"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("group_conversations.id", ondelete="CASCADE")
    )
    agent_config_id: Mapped[int] = mapped_column(ForeignKey("agent_configs.id"))
    role: Mapped[str] = mapped_column(String(20), default="member")
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    conversation: Mapped["GroupConversation"] = relationship(back_populates="members")
    agent: Mapped["AgentConfig"] = relationship()


class GroupChatMessage(Base):
    """团队共享消息流中的一条消息。"""

    __tablename__ = "group_chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("group_conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(20))
    sender_name: Mapped[str] = mapped_column(String(100), default="")
    agent_config_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_configs.id"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text)
    mentions: Mapped[list] = mapped_column(JSON, default=list)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    conversation: Mapped["GroupConversation"] = relationship(back_populates="messages")
    agent: Mapped["AgentConfig"] = relationship()


class GroupMemory(Base):
    """所有团队成员都可读取的共享记忆。"""

    __tablename__ = "group_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("group_conversations.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(100), default="human")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    conversation: Mapped["GroupConversation"] = relationship(back_populates="memories")


class GroupFile(Base):
    """团队共享空间中的 UTF-8 文本文件。"""

    __tablename__ = "group_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("group_conversations.id", ondelete="CASCADE")
    )
    filename: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text, default="")
    content_type: Mapped[str] = mapped_column(String(100), default="text/plain")
    size: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(100), default="human")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    conversation: Mapped["GroupConversation"] = relationship(back_populates="files")


# ---------- 第 3 章新增：知识库三表 ----------
class KnowledgeTag(Base):
    """文档标签：为文档归类，rag 数字员工据此圈定知识范围。"""

    __tablename__ = "knowledge_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class KnowledgeDocument(Base):
    """知识文档：保存清洗后的全文与元数据，是分块与检索的来源。"""

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(300), default="")
    version: Mapped[str] = mapped_column(String(50), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    file_type: Mapped[str] = mapped_column(String(20), default="markdown")  # markdown / txt（预留 pdf 等）
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / indexed / failed
    # 过期时间：为空表示长期有效；仅有效期内文档参与检索。
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    tags: Mapped[list["KnowledgeTag"]] = relationship(secondary=document_tags)
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunk.chunk_index",
    )


class KnowledgeChunk(Base):
    """知识片段：文档分块后的最小检索单元，保留原文与来源标题。"""

    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id"))
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    source_title: Mapped[str] = mapped_column(String(300), default="")
    # 向量随片段一起存库；嵌入失败时为空，检索阶段自动降级关键词匹配。
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding_model_name: Mapped[str] = mapped_column(String(100), default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    document: Mapped["KnowledgeDocument"] = relationship(back_populates="chunks")


# ---------- 第 4 章新增：工具、Agent 工具绑定与长期记忆 ----------
class ToolConfig(Base):
    """预设工具或前端创建的 HTTP API 工具。"""

    __tablename__ = "tool_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    tool_type: Mapped[str] = mapped_column(String(20), default="http")  # builtin / http
    description: Mapped[str] = mapped_column(Text, default="")
    parameters_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    is_enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    agent_bindings: Mapped[list["ReActAgentTool"]] = relationship(
        back_populates="tool",
        cascade="all, delete-orphan",
    )
    policy: Mapped["ToolPolicy | None"] = relationship(
        back_populates="tool", cascade="all, delete-orphan", uselist=False
    )


class ReActAgentTool(Base):
    """ReActAgent 与工具的绑定，以及该 Agent 独有的工具超参数。"""

    __tablename__ = "react_agent_tools"

    agent_config_id: Mapped[int] = mapped_column(
        ForeignKey("agent_configs.id", ondelete="CASCADE"), primary_key=True
    )
    tool_config_id: Mapped[int] = mapped_column(
        ForeignKey("tool_configs.id", ondelete="CASCADE"), primary_key=True
    )
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    agent: Mapped["AgentConfig"] = relationship(back_populates="tool_bindings")
    tool: Mapped["ToolConfig"] = relationship(back_populates="agent_bindings")


class AgentSkillBinding(Base):
    """ReActAgent 可发现的受控技能。"""

    __tablename__ = "agent_skill_bindings"

    agent_config_id: Mapped[int] = mapped_column(
        ForeignKey("agent_configs.id", ondelete="CASCADE"), primary_key=True
    )
    skill_name: Mapped[str] = mapped_column(String(100), primary_key=True)

    agent: Mapped["AgentConfig"] = relationship(back_populates="skill_bindings")


class ToolPolicy(Base):
    """工具风险策略，由程序而不是提示词执行。"""

    __tablename__ = "tool_policies"

    tool_config_id: Mapped[int] = mapped_column(
        ForeignKey("tool_configs.id", ondelete="CASCADE"), primary_key=True
    )
    risk_level: Mapped[str] = mapped_column(String(20), default="write")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    tool: Mapped["ToolConfig"] = relationship(back_populates="policy")


class HarnessRun(Base):
    """一次可暂停、可恢复的 Harness 请求。"""

    __tablename__ = "harness_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("conversation_sessions.id", ondelete="CASCADE"))
    agent_config_id: Mapped[int] = mapped_column(ForeignKey("agent_configs.id", ondelete="CASCADE"))
    assistant_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(30), default="web")
    sender_id: Mapped[str] = mapped_column(String(100), default="anonymous")
    status: Mapped[str] = mapped_column(String(20), default="running")
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ApprovalRequest(Base):
    """高风险工具的人工决定记录。"""

    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("harness_runs.id", ondelete="CASCADE"))
    tool_name: Mapped[str] = mapped_column(String(100))
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_level: Mapped[str] = mapped_column(String(20), default="write")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    decision_channel: Mapped[str] = mapped_column(String(30), default="")
    decision_sender_id: Mapped[str] = mapped_column(String(100), default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HumanRequest(Base):
    """ReAct 循环内等待人工补充的确认或短文本。"""

    __tablename__ = "human_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("harness_runs.id", ondelete="CASCADE"))
    tool_call_id: Mapped[str] = mapped_column(String(200))
    question: Mapped[str] = mapped_column(Text)
    input_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    answer: Mapped[str] = mapped_column(Text, default="")
    response_channel: Mapped[str] = mapped_column(String(30), default="")
    response_sender_id: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditEvent(Base):
    """脱敏后的结构化执行审计。"""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("harness_runs.id", ondelete="CASCADE"), nullable=True
    )
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(50))
    channel: Mapped[str] = mapped_column(String(30), default="")
    sender_id: Mapped[str] = mapped_column(String(100), default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Diary(Base):
    """按作用域和日期维护的 Markdown 日记。"""

    __tablename__ = "diaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    diary_key: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str] = mapped_column(String(20))  # global / agent
    agent_config_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_configs.id", ondelete="CASCADE"), nullable=True
    )
    diary_date: Mapped[date] = mapped_column(default=date.today)
    content: Mapped[str] = mapped_column(Text)
    consolidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding_model_name: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    agent: Mapped["AgentConfig"] = relationship()


class CoreMemory(Base):
    """由日记巩固形成的事实或经验。"""

    __tablename__ = "core_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str] = mapped_column(String(20))  # global / agent
    category: Mapped[str] = mapped_column(String(20))  # fact / experience
    agent_config_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_configs.id", ondelete="CASCADE"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding_model_name: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    agent: Mapped["AgentConfig"] = relationship()

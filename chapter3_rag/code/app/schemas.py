"""Pydantic 请求/响应模型。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------- 模型配置 ----------
class ModelConfigIn(BaseModel):
    name: str
    provider: str = "openai"
    base_url: str
    model_name: str
    api_key: str = ""
    config_type: str = "chat"  # chat / embedding
    dimensions: int | None = None
    is_active: bool = True


class ModelConfigOut(ModelConfigIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class ActiveIn(BaseModel):
    is_active: bool


# ---------- 数字员工配置 ----------
class AgentConfigIn(BaseModel):
    name: str
    agent_type: str = "chatbot"  # chatbot / rag_chatbot
    model_config_id: int
    role: str = ""
    service_goal: str = ""
    business_context: str = ""
    constraints: str = ""
    output_instruction: str = ""
    temperature: float = 0.2
    top_p: float = 1.0
    max_tokens: int = 500
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    history_turns: int = 5
    # RAG 配置
    knowledge_tag_ids: list[int] = Field(default_factory=list)
    retrieval_top_k: int = 3
    retriever_type: str = "vector"  # vector / keyword / hybrid
    status: str = "draft"
    extensions: dict = Field(default_factory=dict)


class AgentConfigOut(AgentConfigIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class StatusIn(BaseModel):
    status: str  # draft / published


# ---------- 会话与消息 ----------
class ConversationIn(BaseModel):
    agent_config_id: int
    language: str = "zh"


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    agent_config_id: int
    language: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    content: str
    extra: dict = Field(default_factory=dict)
    created_at: datetime


class MessageIn(BaseModel):
    content: str


# ---------- 标签 ----------
class TagIn(BaseModel):
    name: str


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    created_at: datetime


# ---------- 知识文档 ----------
class DocumentIn(BaseModel):
    name: str
    source: str = ""
    version: str = ""
    content: str = ""
    file_type: str = "markdown"
    expires_at: datetime | None = None
    tag_ids: list[int] = Field(default_factory=list)


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    chunk_index: int
    content: str
    source_title: str
    embedding_model_name: str = ""


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    source: str
    version: str
    file_type: str
    status: str
    expires_at: datetime | None
    chunk_count: int
    tags: list[TagOut]
    created_at: datetime
    updated_at: datetime


class DocumentDetailOut(DocumentOut):
    content: str
    chunks: list[ChunkOut]


# ---------- 检索调试 ----------
class SearchIn(BaseModel):
    query: str
    tag_ids: list[int] = Field(default_factory=list)
    retriever_type: str = "vector"
    top_k: int = 3


class PassageOut(BaseModel):
    document_id: int
    document_name: str
    source_title: str
    embedding_model_name: str
    content: str
    score: float

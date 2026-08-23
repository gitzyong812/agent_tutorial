"""Pydantic 请求/响应模型。"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import (
    DEFAULT_AGENT_MAX_STEPS,
    DEFAULT_AGENT_MAX_TOKENS,
    MAX_AGENT_MAX_STEPS,
)

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
class AgentToolBinding(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tool_config_id: int
    extra: dict = Field(default_factory=dict)


class AgentConfigData(BaseModel):
    """数字员工的公共字段。输出时只校验类型，兼容已有数据。"""

    name: str
    agent_type: str = "chatbot"
    model_config_id: int
    role: str = ""
    service_goal: str = ""
    business_context: str = ""
    constraints: str = ""
    output_instruction: str = ""
    temperature: float = 0.2
    top_p: float = 1.0
    max_tokens: int = DEFAULT_AGENT_MAX_TOKENS
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    history_turns: int = 5
    # RAG 配置
    knowledge_tag_ids: list[int] = Field(default_factory=list)
    retrieval_top_k: int = 3
    retriever_type: str = "vector"
    # ReActAgent 配置
    tool_bindings: list[AgentToolBinding] = Field(default_factory=list)
    skill_names: list[str] = Field(default_factory=list)
    max_steps: int = DEFAULT_AGENT_MAX_STEPS
    memory_enabled: bool = True
    status: str = "draft"
    extensions: dict = Field(default_factory=dict)


class AgentConfigIn(AgentConfigData):
    """创建和编辑数字员工时使用，负责约束用户输入。"""

    name: str = Field(max_length=100)
    agent_type: Literal["chatbot", "rag_chatbot", "react_agent"] = "chatbot"
    history_turns: int = Field(default=5, ge=0, le=100)
    retrieval_top_k: int = Field(default=3, ge=1, le=20)
    retriever_type: Literal["vector", "keyword", "hybrid"] = "vector"
    max_steps: int = Field(default=DEFAULT_AGENT_MAX_STEPS, ge=1, le=MAX_AGENT_MAX_STEPS)
    status: Literal["draft", "published"] = "draft"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("数字员工名称不能为空")
        return value


class AgentConfigOut(AgentConfigData):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class StatusIn(BaseModel):
    status: Literal["draft", "published"]


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


class ConversationChannelOut(BaseModel):
    channel: str
    status: str
    qr_image: str | None = None
    last_error: str = ""


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


# ---------- HTTP 工具 ----------
class ToolConfigIn(BaseModel):
    name: str
    description: str = ""
    parameters_schema: dict = Field(default_factory=lambda: {"type": "object", "properties": {}})
    method: str = "GET"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    is_enabled: bool = True
    risk_level: Literal["read", "write", "restricted"] = "write"


class ToolOut(ToolConfigIn):
    id: int
    tool_type: str
    method: str | None = None
    url: str | None = None
    source: str  # builtin / custom
    editable: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------- Harness 通道与人工确认 ----------
class StandardRequest(BaseModel):
    session_id: int
    channel: Literal["web", "cli", "weixin"] = "web"
    sender_id: str = Field(default="anonymous", min_length=1, max_length=100)
    content: str = Field(min_length=1)


class ApprovalDecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    channel: Literal["web", "cli"] = "web"
    sender_id: str = Field(default="anonymous", min_length=1, max_length=100)


class HumanAnswerIn(BaseModel):
    answer: str = Field(max_length=4000)
    channel: Literal["web", "cli"] = "web"
    sender_id: str = Field(default="anonymous", min_length=1, max_length=100)


# ---------- 技能管理 ----------
class SkillUpdateIn(BaseModel):
    content: str = Field(min_length=1)


# ---------- 长期记忆 ----------
class DiaryUpdateIn(BaseModel):
    content: str


class CoreMemoryUpdateIn(BaseModel):
    name: str = Field(max_length=200)
    category: Literal["fact", "experience"]
    content: str


class DiaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    scope: str
    agent_config_id: int | None
    content: str
    diary_date: date
    consolidated_at: datetime | None
    embedding_model_name: str
    created_at: datetime
    updated_at: datetime


class CoreMemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    scope: str
    category: str
    agent_config_id: int | None
    content: str
    embedding_model_name: str
    created_at: datetime
    updated_at: datetime


class MemoryPageOut(BaseModel):
    items: list[DiaryOut | CoreMemoryOut]
    total: int
    page: int
    page_size: int
    pages: int


class ConsolidateIn(BaseModel):
    scope: Literal["global", "agent"] = "global"
    agent_config_id: int | None = None

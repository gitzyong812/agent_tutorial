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
    agent_type: str = "chatbot"
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
    created_at: datetime


class MessageIn(BaseModel):
    content: str

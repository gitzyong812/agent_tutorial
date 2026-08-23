"""数字员工多态运行时：按 agent_type 分派不同的对话准备逻辑。"""
from .. import models
from .base import AgentRunner
from .chatbot import ChatbotRunner
from .rag import RagRunner
from .react import ReactRunner

# agent_type -> Runner 类。新增类型在此注册即可，无需改动对话主流程。
_RUNNERS = {
    "chatbot": ChatbotRunner,
    "rag_chatbot": RagRunner,
    "react_agent": ReactRunner,
}


def get_runner(db, agent: models.AgentConfig) -> AgentRunner:
    """根据数字员工类型返回对应运行时；未知类型回退到 ChatbotRunner。"""
    runner_cls = _RUNNERS.get(agent.agent_type, ChatbotRunner)
    return runner_cls(db, agent)


__all__ = ["AgentRunner", "ChatbotRunner", "RagRunner", "ReactRunner", "get_runner"]

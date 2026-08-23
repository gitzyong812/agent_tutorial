"""运行时基类：定义对话准备接口，封装公共的消息组装逻辑。

每种数字员工通过子类实现 build_messages，返回 (messages, sources)：
- messages：发给大模型的消息列表。
- sources：检索到的依据片段（仅 RAG 有），用于前端展示与依据追溯。
"""
from collections.abc import Sequence

from .. import models
from ..rag.retriever import Passage


class AgentRunner:
    """运行时基类。子类按数字员工类型实现 build_messages。"""

    def __init__(self, db, agent: models.AgentConfig):
        self.db = db
        self.agent = agent

    def recent_history(self, history: Sequence[models.ChatMessage]) -> list[models.ChatMessage]:
        """取最近 history_turns 轮完整问答。"""
        agent = self.agent
        if agent.history_turns <= 0:
            return []
        return list(history[-(agent.history_turns * 2):])

    def build_messages(
        self,
        history: Sequence[models.ChatMessage],
        user_input: str,
        language: str = "zh",
    ) -> tuple[list[dict], list[Passage]]:
        """组装发送给模型的消息列表与依据片段。子类实现。"""
        raise NotImplementedError

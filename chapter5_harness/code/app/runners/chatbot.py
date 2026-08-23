"""ChatBot 运行时：第 2 章的基础对话行为。"""
from collections.abc import Sequence

from .. import llm, models
from ..rag.retriever import Passage
from .base import AgentRunner


class ChatbotRunner(AgentRunner):
    """基础对话：系统提示词 + 最近历史 + 本轮输入，不做检索。"""

    def build_messages(
        self,
        history: Sequence[models.ChatMessage],
        user_input: str,
        language: str = "zh",
    ) -> tuple[list[dict], list[Passage]]:
        previous = self.recent_history(history)
        messages = [
            {"role": "system", "content": llm.build_system_prompt(self.agent, language)},
            *[{"role": m.role, "content": m.content} for m in previous],
            {"role": "user", "content": user_input},
        ]
        return messages, []

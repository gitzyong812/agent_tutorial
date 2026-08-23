"""把用户目标规划为带依赖关系的数字员工任务。"""
import json
import re
from dataclasses import dataclass

from openai import OpenAI

from .. import config, models

MAX_PLANNER_CONTEXT_CHARS = 1200
MAX_PLANNER_TASKS = 12


@dataclass
class MentionOccurrence:
    agent: models.AgentConfig
    start: int
    end: int


@dataclass
class AgentTask:
    id: str
    agent: models.AgentConfig
    content: str
    depends_on: list[str]


class TaskPlanner:
    DEPENDENCY_SIGNALS = (
        "基于上面", "基于上一", "基于前面", "根据上面", "根据上一", "根据前面",
        "在此基础", "上面的答案", "上一题", "上一步", "上一个", "前一个",
        "previous", "above", "then", "based on the above", "based on previous",
        "previous answer", "previous result", "on that basis", "continue from",
        "на основе предыдущ", "на основе выше", "предыдущий ответ",
        "предыдущий результат", "на этой основе", "затем", "после этого",
    )

    def __init__(
        self,
        group: models.GroupConversation,
        mentioned_agent_ids: list[int],
        content: str,
    ):
        self.group = group
        self.mentioned_agent_ids = mentioned_agent_ids
        self.content = content or ""

    def build(self) -> list[AgentTask]:
        explicit = self._explicit_mention_occurrences()
        if self._should_use_llm_planner(explicit):
            tasks = self._build_with_llm(explicit)
            if tasks:
                return tasks
        return self._build_with_keywords(explicit)

    def _build_with_keywords(
        self, explicit: list[MentionOccurrence] | None = None
    ) -> list[AgentTask]:
        occurrences = explicit or self._fallback_mention_occurrences()
        tasks: list[AgentTask] = []
        barrier_ids: list[str] = []
        for index, occurrence in enumerate(occurrences):
            content = self._task_content_for_occurrence(occurrences, index)
            task_id = f"task-{index + 1}"
            if tasks and self.is_dependent_task(content):
                dependencies = [tasks[-1].id]
                barrier_ids = [task_id]
            else:
                dependencies = list(barrier_ids)
            tasks.append(AgentTask(task_id, occurrence.agent, content, dependencies))
        return tasks

    def _build_with_llm(self, explicit: list[MentionOccurrence]) -> list[AgentTask]:
        agents = self._planner_agents(explicit)
        planner_model = self._planner_model(agents)
        if not agents or planner_model is None:
            return []
        try:
            client = OpenAI(
                api_key=planner_model["api_key"],
                base_url=planner_model["base_url"],
            )
            response = client.chat.completions.create(
                model=planner_model["model_name"],
                messages=self._planner_messages(agents, explicit),
                temperature=0,
                max_tokens=config.GROUP_TASK_PLANNER_MAX_TOKENS,
            )
            return self._tasks_from_llm_payload(
                response.choices[0].message.content or "", agents
            )
        except Exception:
            return []

    def _should_use_llm_planner(self, explicit: list[MentionOccurrence]) -> bool:
        return config.GROUP_TASK_PLANNER_MODE == "llm" and len(explicit) != 1

    @staticmethod
    def _planner_model(agents: list[models.AgentConfig]) -> dict | None:
        if (
            config.GROUP_TASK_PLANNER_API_KEY
            and config.GROUP_TASK_PLANNER_BASE_URL
            and config.GROUP_TASK_PLANNER_MODEL_NAME
        ):
            return {
                "api_key": config.GROUP_TASK_PLANNER_API_KEY,
                "base_url": config.GROUP_TASK_PLANNER_BASE_URL,
                "model_name": config.GROUP_TASK_PLANNER_MODEL_NAME,
            }
        for agent in agents:
            model = getattr(agent, "model", None)
            if (
                model is not None
                and getattr(model, "is_active", True)
                and getattr(model, "api_key", "")
                and getattr(model, "base_url", "")
                and getattr(model, "model_name", "")
            ):
                return {
                    "api_key": model.api_key,
                    "base_url": model.base_url,
                    "model_name": model.model_name,
                }
        return None

    def _planner_agents(self, explicit: list[MentionOccurrence]) -> list[models.AgentConfig]:
        if explicit:
            return self._unique_agents([item.agent for item in explicit])
        members = self._active_members()
        if not self.mentioned_agent_ids:
            return members
        by_id = {agent.id: agent for agent in members}
        return [by_id[item] for item in self.mentioned_agent_ids if item in by_id]

    def _planner_messages(
        self, agents: list[models.AgentConfig], explicit: list[MentionOccurrence]
    ) -> list[dict]:
        payload = {
            "group": {"title": self.group.title, "language": self.group.language},
            "user_message": self.content,
            "mentioned_agents": [self._agent_brief(item.agent) for item in explicit],
            "available_agents": [self._agent_brief(agent) for agent in agents],
            "recent_messages": self._recent_message_briefs(),
            "memories": self._memory_briefs(),
            "files": self._file_briefs(),
        }
        return [
            {
                "role": "system",
                "content": (
                    "你是多智能体团队的任务规划器。只返回 JSON，不要返回 Markdown。\n"
                    "根据用户目标、团队上下文和成员职责拆分任务并分配角色。\n"
                    '返回格式：{"tasks":[{"agent_id":数字,"content":"任务内容",'
                    '"depends_on":["task-1"]}]}。\n'
                    "依赖只能引用前面已定义的任务。没有依赖时使用空数组。"
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

    def _tasks_from_llm_payload(
        self, raw: str, agents: list[models.AgentConfig]
    ) -> list[AgentTask]:
        payload = self._parse_planner_json(raw)
        items = payload.get("tasks") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []
        by_id = {agent.id: agent for agent in agents}
        tasks = []
        for item in items[:MAX_PLANNER_TASKS]:
            if not isinstance(item, dict):
                return []
            agent = by_id.get(item.get("agent_id"))
            content = str(item.get("content") or "").strip()
            depends_on = item.get("depends_on") or []
            previous_ids = {task.id for task in tasks}
            if (
                agent is None
                or not content
                or not isinstance(depends_on, list)
                or any(item not in previous_ids for item in depends_on)
            ):
                return []
            tasks.append(AgentTask(f"task-{len(tasks) + 1}", agent, content, depends_on))
        return tasks

    @staticmethod
    def _parse_planner_json(raw: str) -> dict:
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text)

    def _explicit_mention_occurrences(self) -> list[MentionOccurrence]:
        by_name = {}
        for agent in self._active_members():
            name = agent.name.casefold()
            by_name[name] = agent
            by_name[name.replace(" ", "-")] = agent
        result = []
        for match in re.finditer(r"@([\w\u4e00-\u9fff-]+)", self.content):
            agent = by_name.get(match.group(1).casefold())
            if agent:
                result.append(MentionOccurrence(agent, match.start(), match.end()))
        return result

    def _active_members(self) -> list[models.AgentConfig]:
        return [
            member.agent for member in self.group.members
            if member.agent.status == "published"
        ]

    def _fallback_mention_occurrences(self) -> list[MentionOccurrence]:
        members = self._active_members()
        by_id = {agent.id: agent for agent in members}
        ids = self.mentioned_agent_ids or [agent.id for agent in members]
        return [
            MentionOccurrence(by_id[item], len(self.content), len(self.content))
            for item in ids if item in by_id
        ]

    def _task_content_for_occurrence(
        self, occurrences: list[MentionOccurrence], index: int
    ) -> str:
        occurrence = occurrences[index]
        next_start = (
            occurrences[index + 1].start if index + 1 < len(occurrences) else len(self.content)
        )
        direct = self.content[occurrence.end:next_start].strip()
        if direct:
            return direct
        for cursor in range(index + 1, len(occurrences)):
            boundary = (
                occurrences[cursor + 1].start
                if cursor + 1 < len(occurrences)
                else len(self.content)
            )
            content = self.content[occurrences[cursor].end:boundary].strip()
            if content:
                return content
        return self.content.strip()

    def _agent_brief(self, agent: models.AgentConfig) -> dict:
        return {
            "id": agent.id,
            "name": agent.name,
            "agent_type": agent.agent_type,
            "role": self._clip(agent.role),
            "service_goal": self._clip(agent.service_goal),
        }

    def _recent_message_briefs(self) -> list[dict]:
        return [
            {
                "role": item.role,
                "sender_name": item.sender_name,
                "content": self._clip(item.content),
            }
            for item in list(self.group.messages)[-8:]
        ]

    def _memory_briefs(self) -> list[dict]:
        return [
            {"key": item.key, "content": self._clip(item.content)}
            for item in list(self.group.memories)[:8]
        ]

    def _file_briefs(self) -> list[dict]:
        return [
            {
                "filename": item.filename,
                "content_type": item.content_type,
                "content": self._clip(item.content),
            }
            for item in list(self.group.files)[:8]
        ]

    @staticmethod
    def _clip(text: str, limit: int = MAX_PLANNER_CONTEXT_CHARS) -> str:
        text = str(text or "")
        return text if len(text) <= limit else text[:limit] + "\n..."

    @staticmethod
    def _unique_agents(agents: list[models.AgentConfig]) -> list[models.AgentConfig]:
        result = []
        seen = set()
        for agent in agents:
            if agent.id not in seen:
                result.append(agent)
                seen.add(agent.id)
        return result

    @classmethod
    def is_dependent_task(cls, text: str) -> bool:
        normalized = (text or "").casefold().replace("ё", "е")
        return any(signal in normalized for signal in cls.DEPENDENCY_SIGNALS)

    @staticmethod
    def task_batches(tasks: list[AgentTask]) -> list[list[AgentTask]]:
        batches = []
        remaining = {task.id: task for task in tasks}
        completed = set()
        while remaining:
            ready = [
                task for task in tasks
                if task.id in remaining
                and all(dependency in completed for dependency in task.depends_on)
            ]
            if not ready:
                unresolved = {task.id: task.depends_on for task in remaining.values()}
                raise ValueError(f"任务依赖图存在循环或未知依赖：{unresolved}")
            batches.append(ready)
            for task in ready:
                completed.add(task.id)
                remaining.pop(task.id)
        return batches


def build_agent_tasks(
    group: models.GroupConversation, mentioned_agent_ids: list[int], content: str
) -> list[AgentTask]:
    return TaskPlanner(group, mentioned_agent_ids, content).build()


def task_batches(tasks: list[AgentTask]) -> list[list[AgentTask]]:
    return TaskPlanner.task_batches(tasks)

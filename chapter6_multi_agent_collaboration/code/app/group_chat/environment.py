"""团队共享环境与各智能体局部上下文的拼装。"""
import re
from types import SimpleNamespace

from .. import models

MAX_PROMPT_FILE_CHARS = 6000


def group_history(messages: list[models.GroupChatMessage]) -> list[SimpleNamespace]:
    history = []
    for message in messages:
        if message.role == "system":
            continue
        prefix = f"{message.sender_name}: " if message.sender_name else ""
        history.append(SimpleNamespace(role=message.role, content=f"{prefix}{message.content}"))
    return history


def environment_prompt(group: models.GroupConversation, user_input: str = "") -> str:
    memories = "\n".join(
        f"- {item.key}: {item.content}" for item in group.memories
    ) or "（暂无共享记忆）"
    referenced = referenced_file_ids(group.files, user_input)
    files = "\n".join(
        file_prompt_line(item, full=item.id in referenced) for item in group.files
    ) or "（暂无共享文件）"
    members = "、".join(member.agent.name for member in group.members)
    return (
        "# 团队共享环境\n"
        f"团队名称：{group.title}\n"
        f"团队成员：{members}\n\n"
        "## 共享记忆\n"
        f"{memories}\n\n"
        "## 共享文件\n"
        f"{files}\n\n"
        "# 协作规则\n"
        "你正在多智能体团队中执行一项局部任务。团队成员共享消息历史、共享记忆和共享文件。"
        "只完成分配给你的任务，不要代替其他成员发言，也不要在回答开头重复自己的名称。"
    )


def with_group_context(
    messages: list[dict], agent: models.AgentConfig, environment: str
) -> list[dict]:
    if not messages:
        return [{"role": "system", "content": environment}]
    first = dict(messages[0])
    first["content"] = (
        f"{environment}\n\n# 当前执行身份\n你是团队中的数字员工：{agent.name}。\n\n"
        f"{first.get('content', '')}"
    )
    return [first, *messages[1:]]


def clean_agent_answer(text: str, current_agent_name: str, member_names: list[str]) -> str:
    lines = []
    for line in (text or "").splitlines():
        matched_name = None
        matched_rest = None
        for name in member_names:
            match = re.match(
                rf"^\s*{re.escape(name)}\s*[:：]\s*(.*)$", line, flags=re.IGNORECASE
            )
            if match:
                matched_name, matched_rest = name, match.group(1)
                break
        if matched_name is None:
            lines.append(line)
        elif matched_name.casefold() == current_agent_name.casefold():
            lines.append(matched_rest or "")
    return "\n".join(lines).strip()


def file_prompt_line(file: models.GroupFile, *, full: bool = False) -> str:
    text = (file.content or "").strip() or "（空文件）"
    limit = len(text) if full else MAX_PROMPT_FILE_CHARS
    if len(text) > limit:
        text = text[:limit] + "\n...（内容过长，已截断）"
    return f"- {file.filename} ({file.content_type}, {file.size} bytes):\n{text}"


def referenced_file_ids(files: list[models.GroupFile], user_input: str) -> set[int]:
    normalized = (user_input or "").replace("\\", "/")
    result = set()
    for file in files:
        basename = file.filename.rsplit("/", 1)[-1]
        if file.filename in normalized or basename in normalized:
            result.add(file.id)
    return result

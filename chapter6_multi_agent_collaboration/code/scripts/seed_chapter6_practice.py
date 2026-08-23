#!/usr/bin/env python3
"""构建第六章多智能体协作实践数据。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_DIR / "chatbot.db"
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app import models  # noqa: E402
from app.database import Base  # noqa: E402
from app.group_chat.files import workspace_path  # noqa: E402


TEAM_TITLE = "校园 AI 创新周宣传团队"
AGENT_SPECS = (
    {
        "name": "事实核查员",
        "role": "你是团队中的事实核查员，负责核对活动时间、地点、对象和限制。",
        "service_goal": "核对共享资料，区分已确认事实与待核实事项。",
        "constraints": "不得补写资料中没有的信息，也不代替其他成员撰写宣传文案。",
        "output_instruction": "输出已确认事实与待核实事项。",
    },
    {
        "name": "渠道分析员",
        "role": "你是团队中的渠道分析员，负责分析公众号、社群和校园海报。",
        "service_goal": "根据活动对象提出传播渠道和发布建议。",
        "constraints": "不修改活动事实，不撰写完整宣传文案。",
        "output_instruction": "输出渠道、目标受众和发布建议。",
    },
    {
        "name": "宣传文案员",
        "role": "你是团队中的宣传文案员，负责依据上游结果形成宣传方案。",
        "service_goal": "根据已确认事实和渠道建议撰写多渠道文案。",
        "constraints": "不得编造未知时间或报名信息。",
        "output_instruction": "输出标题、正文和渠道版本。",
    },
    {
        "name": "内容审核员",
        "role": "你是团队中的内容审核员，负责检查事实、措辞和发布风险。",
        "service_goal": "根据共享资料和上游文案给出审核结论。",
        "constraints": "发现未确认信息时必须明确指出。",
        "output_instruction": "输出通过或退回结论，并列出修改意见。",
    },
)
SHARED_MEMORIES = (
    ("workspace", "团队成员共享当前会话、共享记忆和共享文本文件。"),
    ("发布规则", "未经确认的信息不得写入正式文案。"),
)
BRIEF_FILENAME = "activity-brief.md"
BRIEF_CONTENT = """# 校园人工智能创新周

- 时间：11月18日至22日
- 地点：大学生活动中心
- 对象：全校师生
- 待核实：报名截止时间
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--model-config-id", type=int)
    return parser.parse_args()


def select_model(db: Session, model_config_id: int | None) -> models.ModelConfig:
    if model_config_id is not None:
        model = db.get(models.ModelConfig, model_config_id)
        if model is None or model.config_type != "chat" or not model.is_active:
            raise ValueError("指定的对话模型不存在或未启用")
        return model
    query = db.query(models.ModelConfig).filter_by(config_type="chat", is_active=True)
    model = query.filter(models.ModelConfig.api_key != "").order_by(models.ModelConfig.id).first()
    model = model or query.order_by(models.ModelConfig.id).first()
    if model is None:
        raise ValueError("没有可用的对话模型，请先在网页的“模型配置”中创建并启用模型")
    return model


def build_practice_data(db: Session, model_config_id: int | None = None) -> dict:
    model = select_model(db, model_config_id)
    agents = []
    for spec in AGENT_SPECS:
        agent = (
            db.query(models.AgentConfig)
            .filter_by(name=spec["name"])
            .order_by(models.AgentConfig.id)
            .first()
        )
        if agent is None:
            agent = models.AgentConfig(name=spec["name"])
            db.add(agent)
        agent.agent_type = "chatbot"
        agent.model_config_id = model.id
        agent.role = spec["role"]
        agent.service_goal = spec["service_goal"]
        agent.business_context = "校园人工智能创新周宣传实践。"
        agent.constraints = spec["constraints"]
        agent.output_instruction = spec["output_instruction"]
        agent.status = "published"
        agents.append(agent)
    db.flush()

    group = (
        db.query(models.GroupConversation)
        .filter_by(title=TEAM_TITLE)
        .order_by(models.GroupConversation.id)
        .first()
    )
    if group is None:
        group = models.GroupConversation(title=TEAM_TITLE, language="zh")
        db.add(group)
        db.flush()
    else:
        group.language = "zh"

    member_ids = {item.agent_config_id for item in group.members}
    for agent in agents:
        if agent.id not in member_ids:
            group.members.append(models.GroupConversationMember(agent_config_id=agent.id))

    for key, content in SHARED_MEMORIES:
        memory = next((item for item in group.memories if item.key == key), None)
        if memory is None:
            memory = models.GroupMemory(key=key, created_by="chapter6-seed")
            group.memories.append(memory)
        memory.content = content

    filename = workspace_path(BRIEF_FILENAME)
    shared_file = next((item for item in group.files if item.filename == filename), None)
    if shared_file is None:
        shared_file = models.GroupFile(filename=filename, created_by="chapter6-seed")
        group.files.append(shared_file)
    shared_file.content = BRIEF_CONTENT
    shared_file.content_type = "text/markdown"
    shared_file.size = len(BRIEF_CONTENT.encode("utf-8"))

    db.commit()
    return {
        "model_id": model.id,
        "agent_ids": [agent.id for agent in agents],
        "group_id": group.id,
    }


def main() -> None:
    args = parse_args()
    database = args.database.expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        result = build_practice_data(db, args.model_config_id)
    print(f"第六章实践数据已就绪：{database}")
    print(f"团队编号：{result['group_id']}")
    print(f"数字员工编号：{', '.join(str(item) for item in result['agent_ids'])}")
    print(f"使用模型编号：{result['model_id']}")


if __name__ == "__main__":
    main()

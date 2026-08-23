"""预置演示数据：仅在空库时写入一次，便于克隆后快速体验。"""
from sqlalchemy.orm import Session

from . import models
from .rag import indexer
from .skills import get_skill_registry
from .tools import BUILTIN_TOOLS


_SKILL_CREATOR_DEFAULT_MARKER = "skill_creator_default_applied"
_HUMAN_TOOLS_DEFAULT_MARKER = "human_tools_default_applied"

# 示例保险知识文档：对应正文「示例健康保障计划」，含基础信息、等待期、
# 理赔材料与“未覆盖事项”（故意保留，用于演示知识不足时的拒答）。
_INSURANCE_DOC = """# 产品基础信息
产品名称：示例健康保障计划
适用人群：18 至 55 周岁，具体以投保规则为准。
保障范围：覆盖合同约定的疾病与意外医疗责任，具体以保险条款为准。

# 等待期
本产品疾病责任等待期为 90 天。等待期内发生的疾病相关申请，应以合同条款为准。
意外责任通常自合同生效起承担，具体以条款约定为准。

# 缴费方式
支持年缴与月缴两种方式。投保人可在投保时选择缴费周期，后续变更以保险公司规则为准。

# 退保说明
犹豫期内退保通常可退还已交保费；犹豫期后退保按合同约定退还现金价值，可能产生损失。

# 理赔材料
常见材料包括身份证明、保单信息、医疗票据、诊断证明和保险公司要求的其他材料。
理赔时效与具体流程以保险公司公布的规则为准。

# 未覆盖事项
本文档不包含具体费率、收益承诺和最终理赔结论。
涉及个体核保结果、具体赔付金额等问题，需以正式文件和人工核实为准。
"""


def seed(db: Session) -> None:
    builtin_configs = _seed_builtin_tools(db)
    _seed_skill_creator_defaults(db)
    _seed_human_tool_defaults(db, builtin_configs)
    # 已有任意模型配置则视为非空库，不再写入。
    if db.query(models.ModelConfig).first() is not None:
        db.commit()
        return

    # 1. 对话模型配置占位
    demo_model = models.ModelConfig(
        name="示例对话模型（请填写 API Key）",
        provider="deepseek",
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        api_key="",
        config_type="chat",
        is_active=True,
    )
    db.add(demo_model)
    db.flush()  # 取得自增 id

    # 2. 示例保险知识文档 + 标签
    tag = models.KnowledgeTag(name="保险条款")
    db.add(tag)
    db.flush()
    doc = models.KnowledgeDocument(
        name="示例健康保障计划知识库",
        source="seed",
        version="v1",
        content=_INSURANCE_DOC,
        file_type="markdown",
        status="pending",
    )
    doc.tags = [tag]
    db.add(doc)
    db.flush()

    # 3. ChatBot 数字员工草稿（沿用第 2 章演示）
    rewriter = models.AgentConfig(
        name="高情商话术改写助手",
        agent_type="chatbot",
        model_config_id=demo_model.id,
        role="你是保险公司内部的销售话术教练，服务对象是一线销售人员，"
        "负责把生硬的表达改写得更专业、亲和、有同理心，沟通风格友好克制。",
        service_goal="把用户给出的原始话术改写为 1~2 个更得体的版本，并简要说明改写思路。",
        business_context=(
            "改写要遵守保险销售合规要求：不夸大收益、不承诺理赔结果、不贬低同业。\n"
            "参考样例：\n"
            "原话：这款产品稳赚不赔，闭眼买就行。\n"
            "改写：这款产品设计兼顾保障与稳健，具体收益以条款约定为准，我可以帮您梳理它是否匹配您的需求。"
        ),
        constraints="不得编造产品条款或收益数字；涉及具体条款、保费、理赔结论时，建议以正式资料和人工确认为准。",
        output_instruction="先给出改写后的话术，再用一句话说明改写要点。",
        status="draft",
    )

    # 4. RAG 数字员工草稿：绑定「保险条款」标签，默认向量检索
    rag_expert = models.AgentConfig(
        name="保险知识问答助手",
        agent_type="rag_chatbot",
        model_config_id=demo_model.id,
        role="你是保险公司内部的保险知识问答数字员工，服务对象是业务人员，沟通风格严谨、清晰。",
        service_goal="依据知识库检索到的资料回答保险咨询问题。",
        business_context="",
        constraints="只依据检索资料回答；资料不足时说明无法确认，并建议人工核实，不要编造。",
        output_instruction="先给结论，再列依据，最后给出必要提醒。",
        knowledge_tag_ids=[tag.id],
        retrieval_top_k=3,
        retriever_type="vector",
        status="draft",
    )

    # 5. ReActAgent 草稿：默认绑定计算和记忆检索工具。
    react_agent = models.AgentConfig(
        name="保险业务助手",
        agent_type="react_agent",
        model_config_id=demo_model.id,
        role="你是保险公司内部的销售任务数字员工，负责查询资料、完成计算并保持任务连续性。",
        service_goal="根据业务人员目标制定必要计划，调用工具取得依据，再给出清晰、可核验的结果。",
        business_context=(
            "这是一个本地教学系统。管理员是使用系统的保险业务人员，客户是保险需求主体。"
            "工具结果是执行事实，长期记忆只保存主体明确的稳定事实和可复用任务经验。"
        ),
        constraints="不得伪造工具结果；涉及产品条款时必须查询知识库；资料不足时建议人工核实。",
        output_instruction="先给结论，再说明使用了哪些资料或计算结果，最后提示必要风险。",
        memory_enabled=True,
        extensions={
            _SKILL_CREATOR_DEFAULT_MARKER: True,
            _HUMAN_TOOLS_DEFAULT_MARKER: True,
        },
        status="draft",
    )

    react_agent.tool_bindings = [
        models.ReActAgentTool(tool_config_id=builtin_configs[name].id, extra=extra)
        for name, extra in {
            "calculator": {},
            "memory_search": {"top_k": 5},
            "knowledge_search": {
                "knowledge_tag_ids": [tag.id],
                "retrieval_top_k": 3,
                "retriever_type": "hybrid",
            },
            "ask_human": {},
            "handoff_to_human": {},
        }.items()
    ]
    registry = get_skill_registry()
    registry.refresh()
    react_agent.skill_bindings = [
        models.AgentSkillBinding(skill_name=name)
        for name in ("skill-creator", "insurance-inquiry")
        if registry.get(name) is not None
    ]

    db.add_all([rewriter, rag_expert, react_agent])
    db.commit()

    # 6. 对示例文档建索引（无 .env 嵌入配置时片段仍入库，status=failed，
    #    待用户配置嵌入模型后可在知识库页重建索引）。
    db.refresh(doc)
    indexer.reindex_document(db, doc)


def _seed_builtin_tools(db: Session) -> dict[str, models.ToolConfig]:
    """幂等补齐预设工具，已有数据库也会执行。"""
    existing = {
        item.name: item
        for item in db.query(models.ToolConfig)
        .filter(models.ToolConfig.name.in_(BUILTIN_TOOLS))
        .all()
    }
    for name, definition in BUILTIN_TOOLS.items():
        item = existing.get(name)
        if item is None:
            item = models.ToolConfig(name=name, tool_type="builtin")
            db.add(item)
            existing[name] = item
        item.tool_type = "builtin"
        item.description = definition["description"]
        item.parameters_schema = definition["parameters"]
        item.method = None
        item.url = None
        item.headers = {}
        item.is_enabled = True
        if item.policy is None:
            item.policy = models.ToolPolicy(risk_level="read")
        else:
            item.policy.risk_level = "read"
    for item in db.query(models.ToolConfig).filter(models.ToolConfig.tool_type == "http").all():
        if item.policy is None:
            item.policy = models.ToolPolicy(risk_level="write")
    db.flush()
    return existing


def _seed_skill_creator_defaults(db: Session) -> None:
    """为已有 ReActAgent 一次性补齐内置 skill-creator。"""
    registry = get_skill_registry()
    registry.refresh()
    if registry.get("skill-creator") is None:
        return
    agents = db.query(models.AgentConfig).filter_by(agent_type="react_agent").all()
    for agent in agents:
        extensions = dict(agent.extensions or {})
        if extensions.get(_SKILL_CREATOR_DEFAULT_MARKER):
            continue
        if "skill-creator" not in {item.skill_name for item in agent.skill_bindings}:
            agent.skill_bindings.append(models.AgentSkillBinding(skill_name="skill-creator"))
        extensions[_SKILL_CREATOR_DEFAULT_MARKER] = True
        agent.extensions = extensions


def _seed_human_tool_defaults(
    db: Session, tools: dict[str, models.ToolConfig]
) -> None:
    """只为新建或首次升级的 ReActAgent 绑定人工协同工具。"""
    agents = db.query(models.AgentConfig).filter_by(agent_type="react_agent").all()
    for agent in agents:
        extensions = dict(agent.extensions or {})
        if extensions.get(_HUMAN_TOOLS_DEFAULT_MARKER):
            continue
        current = {item.tool.name for item in agent.tool_bindings}
        for name in ("ask_human", "handoff_to_human"):
            if name not in current:
                agent.tool_bindings.append(
                    models.ReActAgentTool(tool_config_id=tools[name].id, extra={})
                )
        extensions[_HUMAN_TOOLS_DEFAULT_MARKER] = True
        agent.extensions = extensions

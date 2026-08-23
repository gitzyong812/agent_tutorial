"""预置演示数据：仅在空库时写入一次，便于克隆后快速体验。"""
from sqlalchemy.orm import Session

from . import models
from .rag import indexer

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
    # 已有任意模型配置则视为非空库，不再写入。
    if db.query(models.ModelConfig).first() is not None:
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

    db.add_all([rewriter, rag_expert])
    db.commit()

    # 5. 对示例文档建索引（无 .env 嵌入配置时片段仍入库，status=failed，
    #    待用户配置嵌入模型后可在知识库页重建索引）。
    db.refresh(doc)
    indexer.reindex_document(db, doc)

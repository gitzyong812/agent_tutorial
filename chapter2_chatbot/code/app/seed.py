"""预置演示数据：仅在空库时写入一次，便于克隆后快速体验。"""
from sqlalchemy.orm import Session

from . import models


def seed(db: Session) -> None:
    # 已有任意模型配置则视为非空库，不再写入。
    if db.query(models.ModelConfig).first() is not None:
        return

    demo_model = models.ModelConfig(
        name="示例模型（请填写 API Key）",
        provider="deepseek",
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        api_key="",
        is_active=False,
    )
    db.add(demo_model)
    db.flush()  # 取得 demo_model.id

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

    expert = models.AgentConfig(
        name="保险政策咨询专家",
        agent_type="chatbot",
        model_config_id=demo_model.id,
        role="你是保险公司内部的政策咨询专家，服务对象是内部业务人员，"
        "负责依据已配置资料解答产品与政策疑问，沟通风格严谨、清晰。",
        service_goal="依据业务资料回答政策类问题，帮助业务人员准确理解产品与流程。",
        business_context="（请在此填写可对外引用的产品与政策资料，可附 1~2 条问答样例。）",
        constraints="资料未覆盖的内容，明确说明无法确认，不要猜测，并建议向人工或正式文件核实。",
        output_instruction="先直接回答，再简要说明依据。",
        status="draft",
    )

    db.add_all([rewriter, expert])
    db.commit()

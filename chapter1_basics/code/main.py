import os

from dotenv import load_dotenv
from openai import OpenAI


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"请在 .env 中配置 {name}")
    return value


def ask_model(client: OpenAI, model: str, system_prompt: str, user_prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""


def main() -> None:
    load_dotenv()

    api_key = require_env("LLM_API_KEY")
    base_url = require_env("LLM_BASE_URL")
    model = require_env("LLM_MODEL")

    client = OpenAI(api_key=api_key, base_url=base_url)

    normal_answer = ask_model(
        client=client,
        model=model,
        system_prompt="你是一个回答简洁、准确的 AI 助手。",
        user_prompt="请用两句话解释什么是大模型。",
    )
    print("普通问答：")
    print(normal_answer)

    role_answer = ask_model(
        client=client,
        model=model,
        system_prompt=(
            "你是一名销售和客服数字员工，回答要礼貌、清晰，"
            "并主动帮助用户理解产品价值。"
        ),
        user_prompt="用户问：你们的智能客服系统适合小公司使用吗？",
    )
    print("\n角色提示词问答：")
    print(role_answer)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"运行失败：{exc}")


# src/aoai_client.py
from typing import List, Dict
import os
from dotenv import load_dotenv
from azure.identity import AzureCliCredential, get_bearer_token_provider
from openai import AzureOpenAI

# 加载 .env
load_dotenv()

DEFAULT_API_VERSION = os.getenv("AOAI_API_VERSION", "2024-02-15-preview")
DEFAULT_TEMPERATURE = float(os.getenv("AOAI_TEMPERATURE", "0.2"))
SCOPE = "https://cognitiveservices.azure.com/.default"

def _get_client() -> AzureOpenAI:
    endpoint = os.getenv("GPT_ENDPOINT")
    if not endpoint:
        raise RuntimeError("Missing GPT_ENDPOINT. 请在 .env 或环境变量里设置 AOAI 终结点。")

    # 使用 Azure CLI 登录获取凭据
    credential = AzureCliCredential()
    token_provider = get_bearer_token_provider(credential, SCOPE)

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version=DEFAULT_API_VERSION,
        max_retries=5,
    )
    return client

def chat_completion(messages: List[Dict[str, str]],
                    deployment: str | None = None,
                    temperature: float | None = None) -> str:
    """
    标准 Chat Completions 调用，返回纯文本 Markdown。
    messages: [{"role": "system"|"user"|"assistant", "content": "..."}, ...]
    deployment: AOAI 部署名（gpt-4o 等）
    """
    if not deployment:
        deployment = os.getenv("AOAI_DEPLOYMENT")
    if not deployment:
        raise RuntimeError("Missing AOAI_DEPLOYMENT. 请设置实际的部署名，如 gpt-4o。")

    if temperature is None:
        temperature = DEFAULT_TEMPERATURE

    client = _get_client()
    kwargs = {"model": deployment, "messages": messages}
    # Some models (e.g. gpt-5) only support the default temperature (1).
    # Omit the parameter entirely when it equals the default to stay compatible.
    if temperature != 1.0:
        kwargs["temperature"] = temperature
    resp = client.chat.completions.create(**kwargs)

    try:
        return resp.choices[0].message.content or ""
    except (IndexError, AttributeError) as e:
        raise RuntimeError(f"Failed to extract response content: {e}") from e

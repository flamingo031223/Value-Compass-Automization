# src/llm_report.py

import os
from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.identity import AzureCliCredential

load_dotenv()

def generate_report(messages):
    endpoint = os.getenv("GPT_ENDPOINT")
    deployment = os.getenv("AOAI_DEPLOYMENT")
    api_version = os.getenv("AOAI_API_VERSION", "2024-02-15-preview")

    if not endpoint or not deployment:
        raise ValueError("AOAI environment variables are not set correctly.")

    # ✅ 强制使用 Azure CLI 登录态（公司智能卡 / sc-account）
    credential = AzureCliCredential()

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_version=api_version,
        azure_ad_token_provider=lambda: credential.get_token(
            "https://cognitiveservices.azure.com/.default"
        ).token,
    )

    response = client.chat.completions.create(
        model=deployment,
        messages=messages,
        temperature=0.2,
        max_tokens=4000,
    )

    return response.choices[0].message.content

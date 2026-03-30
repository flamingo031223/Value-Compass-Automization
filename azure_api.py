import os 
from azure.identity import get_bearer_token_provider, AzureCliCredential 
from openai import AzureOpenAI 

# If you're using your corp account 
credential = AzureCliCredential()
endpoint = os.getenv("ENDPOINT_URL", "https://jing-east-us-2.openai.azure.com/")
deployment = os.getenv("DEPLOYMENT_NAME", "gpt-5") # "gpt-4.1")

token_provider = get_bearer_token_provider( 
    credential, 
    "https://cognitiveservices.azure.com/.default") 

aoiclient = AzureOpenAI( 
    azure_endpoint=endpoint, 
    azure_ad_token_provider=token_provider, 
    api_version="2025-01-01-preview",
    max_retries=5, 
)

messages = [{"role": "user", "content": "What is the meaning of life?"}]
response = aoiclient.chat.completions.create(
                model=deployment,
                messages=messages,
                # max_tokens=128,
                max_completion_tokens=128 + 2000,
                temperature=1.0,
                # top_p=0.95,
                reasoning_effort="minimal",
            )
print(response.choices[0].message.content)
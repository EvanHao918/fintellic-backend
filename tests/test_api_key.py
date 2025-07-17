from openai import OpenAI
from app.core.config import settings

print(f"API Key (first 10 chars): {settings.OPENAI_API_KEY[:10]}...")
print(f"API Key (last 4 chars): ...{settings.OPENAI_API_KEY[-4:]}")

try:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say hello"}],
        max_tokens=10
    )
    print("✅ API Key is valid!")
    print(f"Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"❌ API Key error: {e}")

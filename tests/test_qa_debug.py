#!/usr/bin/env python3
"""
Debug Q&A generation
"""
from dotenv import load_dotenv
load_dotenv()

import asyncio
from openai import OpenAI
from app.core.config import settings

# Sample content from the 8-K
content = """
On May 12, 2025, Apple Inc. consummated the issuance and sale of $1,500,000,000 aggregate principal amount of its 4.000% Notes due 2028, $1,000,000,000 aggregate principal amount of its 4.200% Notes due 2030, $1,000,000,000 aggregate principal amount of its 4.500% Notes due 2032 and $1,000,000,000 aggregate principal amount of its 4.750% Notes due 2035.
"""

async def test_qa_generation():
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    prompt = f"""Based on this 8-K filing from Apple Inc., generate 3-5 key questions an investor would want answered, along with brief answers based on the filing content.

Content:
{content}

Format as JSON array:
[
    {{
        "question": "Question text",
        "answer": "Answer based on filing (50-100 words)"
    }}
]"""

    print("Sending prompt to OpenAI...")
    print("-" * 50)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful financial analyst."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.3
        )
        
        result = response.choices[0].message.content.strip()
        print("Raw response:")
        print(result)
        print("-" * 50)
        
        # Try to parse JSON
        import json
        try:
            questions = json.loads(result)
            print(f"\nParsed {len(questions)} questions:")
            for i, qa in enumerate(questions, 1):
                print(f"\nQ{i}: {qa['question']}")
                print(f"A{i}: {qa['answer']}")
        except json.JSONDecodeError as e:
            print(f"\nJSON parse error: {e}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_qa_generation())
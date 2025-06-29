#!/usr/bin/env python3
"""
Simple test for AI processing
"""
from dotenv import load_dotenv
load_dotenv()  # Load .env file first

import os
import asyncio
from openai import OpenAI

# Test OpenAI connection
api_key = os.getenv('OPENAI_API_KEY')
print(f"API Key loaded: {'Yes' if api_key else 'No'}")

if api_key:
    print(f"API Key starts with: {api_key[:20]}...")
    
    # Test OpenAI API
    try:
        client = OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'Hello, Fintellic!' in 5 words or less."}
            ],
            max_tokens=50
        )
        
        print(f"\nOpenAI Response: {response.choices[0].message.content}")
        print("\n✅ OpenAI API is working!")
        
    except Exception as e:
        print(f"\n❌ OpenAI API Error: {e}")
else:
    print("\n❌ No API key found")
    print("Current directory:", os.getcwd())
    print(".env exists:", os.path.exists('.env'))
"""
Diagnose OpenAI API Key issues
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

def check_env_files():
    """Check all possible .env file locations"""
    print("=" * 50)
    print("Checking .env files")
    print("=" * 50)
    
    # Possible .env locations
    locations = [
        ".env",
        ".env.local",
        ".env.development",
        "../.env",
        Path.home() / ".env"
    ]
    
    for loc in locations:
        if os.path.exists(loc):
            print(f"\n✅ Found: {loc}")
            with open(loc, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    if "OPENAI_API_KEY" in line:
                        # Don't print the actual key
                        if "=" in line:
                            key_part = line.split("=")[1].strip()[:10]
                            print(f"   OPENAI_API_KEY = {key_part}...")
        else:
            print(f"❌ Not found: {loc}")

def check_environment_variables():
    """Check environment variables"""
    print("\n" + "=" * 50)
    print("Checking Environment Variables")
    print("=" * 50)
    
    # Check if key is in environment
    api_key = os.getenv("OPENAI_API_KEY")
    
    if api_key:
        print(f"✅ OPENAI_API_KEY found in environment")
        print(f"   Length: {len(api_key)} characters")
        print(f"   Starts with: {api_key[:7]}...")
        print(f"   Format: {'Valid' if api_key.startswith('sk-') else 'Invalid'}")
    else:
        print("❌ OPENAI_API_KEY not found in environment")
    
    # Check other related vars
    print("\n📋 Other environment variables:")
    for key in os.environ:
        if "OPENAI" in key or "API" in key:
            print(f"   {key} = {os.environ[key][:20]}...")

def check_dotenv_loading():
    """Check different ways of loading .env"""
    print("\n" + "=" * 50)
    print("Testing dotenv Loading Methods")
    print("=" * 50)
    
    # Method 1: Basic load_dotenv
    print("\n1. Basic load_dotenv():")
    load_dotenv()
    key1 = os.getenv("OPENAI_API_KEY")
    print(f"   Result: {'Found' if key1 else 'Not found'}")
    
    # Method 2: With override
    print("\n2. load_dotenv(override=True):")
    load_dotenv(override=True)
    key2 = os.getenv("OPENAI_API_KEY")
    print(f"   Result: {'Found' if key2 else 'Not found'}")
    
    # Method 3: Find and load
    print("\n3. Using find_dotenv():")
    dotenv_path = find_dotenv()
    if dotenv_path:
        print(f"   Found .env at: {dotenv_path}")
        load_dotenv(dotenv_path)
        key3 = os.getenv("OPENAI_API_KEY")
        print(f"   Result: {'Found' if key3 else 'Not found'}")
    else:
        print("   No .env file found by find_dotenv()")

def check_app_config():
    """Check how the app loads the config"""
    print("\n" + "=" * 50)
    print("Checking App Configuration")
    print("=" * 50)
    
    try:
        # Add parent directory to path
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        from app.core.config import settings
        
        print("✅ Successfully imported settings")
        
        if hasattr(settings, 'OPENAI_API_KEY'):
            key = settings.OPENAI_API_KEY
            if key:
                print(f"✅ OPENAI_API_KEY found in settings")
                print(f"   Length: {len(key)} characters")
                print(f"   Starts with: {key[:7]}...")
            else:
                print("❌ OPENAI_API_KEY is None in settings")
        else:
            print("❌ OPENAI_API_KEY not found in settings")
            
    except Exception as e:
        print(f"❌ Error importing settings: {e}")

def test_openai_connection():
    """Test actual OpenAI connection"""
    print("\n" + "=" * 50)
    print("Testing OpenAI Connection")
    print("=" * 50)
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ No API key to test")
        return
    
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key)
        
        # Simple test
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Say 'API key works!'"}],
            max_tokens=10
        )
        
        print("✅ OpenAI API connection successful!")
        print(f"   Response: {response.choices[0].message.content}")
        
    except Exception as e:
        print(f"❌ OpenAI API test failed: {e}")
        
        # Check error details
        error_str = str(e)
        if "401" in error_str:
            print("   → API key is invalid or expired")
        elif "429" in error_str:
            print("   → Rate limit exceeded")
        elif "timeout" in error_str:
            print("   → Connection timeout")

def check_key_format():
    """Check API key format issues"""
    print("\n" + "=" * 50)
    print("Checking API Key Format")
    print("=" * 50)
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ No key to check")
        return
    
    # Common issues
    issues = []
    
    if api_key.startswith('"') or api_key.endswith('"'):
        issues.append("Key has quotes - remove them")
    
    if api_key.startswith("'") or api_key.endswith("'"):
        issues.append("Key has single quotes - remove them")
    
    if " " in api_key:
        issues.append("Key contains spaces")
    
    if "\n" in api_key or "\r" in api_key:
        issues.append("Key contains newline characters")
    
    if not api_key.startswith("sk-"):
        issues.append("Key doesn't start with 'sk-'")
    
    if len(api_key) < 40:
        issues.append(f"Key seems too short ({len(api_key)} chars)")
    
    if issues:
        print("❌ Found issues with API key format:")
        for issue in issues:
            print(f"   - {issue}")
    else:
        print("✅ API key format looks correct")

def main():
    """Run all diagnostics"""
    print("OpenAI API Key Diagnostics")
    print("=" * 50)
    
    check_env_files()
    check_environment_variables()
    check_dotenv_loading()
    check_app_config()
    check_key_format()
    test_openai_connection()
    
    print("\n" + "=" * 50)
    print("Diagnostic Summary")
    print("=" * 50)
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    if api_key:
        if api_key.startswith("sk-proj-"):
            print("⚠️  You have a project-scoped API key")
            print("   These keys may have limited permissions")
            print("   Try creating a new secret key at:")
            print("   https://platform.openai.com/api-keys")
        elif api_key.startswith("sk-"):
            print("✅ API key format is correct")
            print("   If it's not working, the key may be:")
            print("   - Expired or revoked")
            print("   - From a different project")
            print("   - Missing required permissions")
    else:
        print("❌ No API key found")
        print("\nTo fix:")
        print("1. Create/check your .env file")
        print("2. Add: OPENAI_API_KEY=sk-your-key-here")
        print("3. Restart your application")

if __name__ == "__main__":
    main()
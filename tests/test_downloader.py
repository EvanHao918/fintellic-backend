#!/usr/bin/env python3
"""
Test filing downloader connection
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from app.services.filing_downloader import filing_downloader


async def main():
    print("Testing connection to SEC EDGAR...")
    result = await filing_downloader.test_connection()
    
    if result:
        print("✅ Connection test passed!")
    else:
        print("❌ Connection test failed!")


if __name__ == "__main__":
    asyncio.run(main())
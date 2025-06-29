#!/usr/bin/env python3
"""
Download the TXT version of the filing
"""
import httpx
import asyncio
from pathlib import Path


async def download_txt_filing():
    """Download the plain text version of the filing"""
    
    # The TXT file URL from the analysis
    txt_url = "https://www.sec.gov/Archives/edgar/data/320193/000114036125018400/0001140361-25-018400.txt"
    
    # Local path to save
    filing_dir = Path("data/filings/0000320193/000114036125018400")
    txt_path = filing_dir / "filing.txt"
    
    print(f"Downloading TXT filing from: {txt_url}")
    
    headers = {
        "User-Agent": "Fintellic/1.0 (contact@fintellic.com)",
        "Accept": "text/plain"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(txt_url, headers=headers, timeout=30.0)
            
            if response.status_code == 200:
                # Save the file
                with open(txt_path, 'wb') as f:
                    f.write(response.content)
                
                print(f"✅ Downloaded successfully!")
                print(f"   File size: {len(response.content):,} bytes")
                print(f"   Saved to: {txt_path}")
                
                # Preview the content
                text = response.text
                print(f"\nFirst 1000 characters:")
                print("=" * 80)
                print(text[:1000])
                print("=" * 80)
                
                # Look for the 8-K content
                if "ITEM" in text.upper():
                    print("\n✅ Found ITEM sections in the document!")
                    
                    # Find and display items
                    lines = text.split('\n')
                    for i, line in enumerate(lines):
                        if 'ITEM' in line.upper() and len(line) < 100:
                            print(f"  Line {i}: {line.strip()}")
                
            else:
                print(f"❌ Failed to download: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(download_txt_filing())
#!/usr/bin/env python3
"""
Test text extraction from downloaded filings
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from app.services.text_extractor import text_extractor


def main():
    print("Text Extraction Test")
    print("=" * 50)
    
    # Find a downloaded filing
    filing_dir = Path("data/filings/0000320193/000114036125018400")
    
    if not filing_dir.exists():
        print("❌ No downloaded filing found")
        print("Please run the downloader first")
        return
    
    print(f"Testing extraction from: {filing_dir}")
    
    # List files in directory
    files = list(filing_dir.glob("*.htm"))
    print(f"\nFiles found: {[f.name for f in files]}")
    
    # Extract text
    print("\nExtracting text...")
    sections = text_extractor.extract_from_filing(filing_dir)
    
    if 'error' in sections:
        print(f"❌ Error: {sections['error']}")
        return
    
    # Show results
    print(f"\n✅ Extraction successful!")
    print(f"\nFull text length: {len(sections.get('full_text', ''))}")
    print(f"Primary content length: {len(sections.get('primary_content', ''))}")
    
    # Show preview of primary content
    primary = sections.get('primary_content', '')
    if primary:
        print("\n" + "="*50)
        print("PRIMARY CONTENT PREVIEW (first 1000 chars):")
        print("="*50)
        print(primary[:1000])
        print("...")
        
        # Save to file for inspection
        output_file = Path("extracted_text_sample.txt")
        with open(output_file, 'w') as f:
            f.write(f"FULL TEXT ({len(sections['full_text'])} chars):\n")
            f.write("="*50 + "\n")
            f.write(sections['full_text'][:5000])
            f.write("\n\n" + "="*50 + "\n")
            f.write(f"PRIMARY CONTENT ({len(primary)} chars):\n")
            f.write("="*50 + "\n")
            f.write(primary)
        
        print(f"\n💾 Full extracted text saved to: {output_file}")


if __name__ == "__main__":
    main()
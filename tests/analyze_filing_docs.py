#!/usr/bin/env python3
"""
Analyze filing documents to understand their structure
"""
import sys
from pathlib import Path
from bs4 import BeautifulSoup

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))


def analyze_index_page(index_path: Path):
    """Analyze the index.htm file to find all documents"""
    print(f"\nAnalyzing index page: {index_path}")
    print("=" * 80)
    
    with open(index_path, 'r', encoding='utf-8', errors='ignore') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
    
    # Find all tables
    tables = soup.find_all('table')
    print(f"Found {len(tables)} tables")
    
    # Look for document links
    all_links = soup.find_all('a')
    doc_links = []
    
    for link in all_links:
        href = link.get('href', '')
        text = link.get_text().strip()
        
        # Skip navigation links
        if href and not href.startswith('#') and not href.startswith('javascript:'):
            # Check if it's a document link
            if any(ext in href.lower() for ext in ['.htm', '.xml', '.txt', '.pdf']):
                doc_links.append({
                    'text': text,
                    'href': href,
                    'type': 'xml' if '.xml' in href else 'html' if '.htm' in href else 'other'
                })
    
    print(f"\nFound {len(doc_links)} document links:")
    for i, doc in enumerate(doc_links, 1):
        print(f"{i}. {doc['text']:<40} Type: {doc['type']:<6} URL: {doc['href']}")
    
    # Look for the actual 8-K content
    print("\n" + "="*80)
    print("Looking for main 8-K document...")
    
    # Find rows with "8-K" in them
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            row_text = row.get_text()
            if '8-k' in row_text.lower():
                print(f"\nFound 8-K reference:")
                print(row_text.strip()[:200])
                
                # Get all links in this row
                row_links = row.find_all('a')
                for link in row_links:
                    print(f"  Link: {link.get_text().strip()} -> {link.get('href', 'No href')}")


def analyze_filing_directory(filing_dir: Path):
    """Analyze all files in a filing directory"""
    print(f"\nAnalyzing filing directory: {filing_dir}")
    print("=" * 80)
    
    if not filing_dir.exists():
        print("Directory not found!")
        return
    
    # List all files
    files = list(filing_dir.iterdir())
    print(f"\nFiles in directory ({len(files)} total):")
    
    for f in sorted(files):
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name:<30} {size_kb:>8.1f} KB")
        
        # Check content type
        if f.suffix in ['.htm', '.html']:
            with open(f, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read(1000)  # First 1000 chars
                
                if 'inline xbrl viewer' in content.lower():
                    print(f"    -> iXBRL viewer container")
                elif '<html' in content.lower():
                    # Count text content
                    soup = BeautifulSoup(content, 'html.parser')
                    text_preview = soup.get_text()[:100].strip()
                    if text_preview:
                        print(f"    -> HTML with text: {text_preview[:50]}...")
                else:
                    print(f"    -> Unknown format")


def main():
    print("SEC Filing Document Analysis")
    print("=" * 80)
    
    # Analyze the filing we downloaded
    filing_dir = Path("data/filings/0000320193/000114036125018400")
    
    if filing_dir.exists():
        # Analyze directory
        analyze_filing_directory(filing_dir)
        
        # Analyze index page
        index_path = filing_dir / "index.htm"
        if index_path.exists():
            analyze_index_page(index_path)
        
        # Try to find any XML files
        xml_files = list(filing_dir.glob("*.xml"))
        if xml_files:
            print(f"\n{'='*80}")
            print(f"Found {len(xml_files)} XML files - these might contain the actual data")
    else:
        print(f"Filing directory not found: {filing_dir}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Fetch current S&P 500 companies list from Wikipedia
This ensures we always have the most up-to-date list
"""
import json
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
import sys
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.append(str(Path(__file__).parent.parent))


def fetch_sp500_from_wikipedia():
    """Fetch current S&P 500 list from Wikipedia"""
    print("Fetching S&P 500 list from Wikipedia...")
    
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        response = httpx.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the main table
        table = soup.find('table', {'id': 'constituents'})
        if not table:
            tables = soup.find_all('table', {'class': 'wikitable'})
            if tables:
                table = tables[0]
            else:
                print("Error: Could not find S&P 500 table")
                return []
        
        companies = []
        rows = table.find_all('tr')[1:]  # Skip header
        print(f"Found {len(rows)} rows in table")
        
        for i, row in enumerate(rows):
            try:
                cols = row.find_all('td')
                if len(cols) >= 7:
                    ticker = cols[0].text.strip()
                    name = cols[1].text.strip()
                    
                    # CIK is in column 6
                    cik_text = cols[6].text.strip()
                    cik = ''.join(filter(str.isdigit, cik_text)).zfill(10)
                    
                    if ticker and name and len(cik) == 10:
                        companies.append({
                            "ticker": ticker,
                            "name": name,
                            "cik": cik
                        })
                    
                    if (i + 1) % 100 == 0:
                        print(f"Processed {i + 1} companies...")
                    
            except Exception as e:
                continue
        
        valid_ciks = len([c for c in companies if c['cik'] != '0000000000'])
        print(f"\nFetched {len(companies)} companies ({valid_ciks} with valid CIKs)")
        
        return companies
        
    except Exception as e:
        print(f"Error: {e}")
        return []


def save_sp500_list(companies):
    """Save S&P 500 list to JSON file"""
    data_dir = Path(__file__).parent.parent / "app" / "data"
    data_dir.mkdir(exist_ok=True)
    
    data = {
        "companies": sorted(companies, key=lambda x: x['ticker']),
        "count": len(companies),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Wikipedia"
    }
    
    json_path = data_dir / "sp500_companies.json"
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\nSaved to: {json_path}")
    
    # Show sample with CIKs
    print("\nSample companies:")
    for company in companies[:10]:
        print(f"  {company['ticker']}: {company['name']} (CIK: {company['cik']})")
    print("  ...")


def main():
    """Main function"""
    print("S&P 500 Company List Fetcher")
    print("=" * 50)
    
    companies = fetch_sp500_from_wikipedia()
    
    if companies:
        save_sp500_list(companies)
        
        print(f"\nStatistics:")
        print(f"- Total companies: {len(companies)}")
        print(f"- Have valid CIKs: {len([c for c in companies if c['cik'] != '0000000000'])}")
    else:
        print("\nFailed to fetch S&P 500 list")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
#!/usr/bin/env python3
"""
Fetch current NASDAQ 100 companies list
"""
import json
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))


def fetch_nasdaq100_from_wikipedia():
    """Fetch current NASDAQ 100 list from Wikipedia"""
    print("Fetching NASDAQ 100 list from Wikipedia...")
    
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        response = httpx.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the components table
        companies = []
        
        # Look for the table containing company data
        tables = soup.find_all('table', {'class': 'wikitable'})
        
        for table in tables:
            # Check if this is the right table by looking for "Ticker" in headers
            headers = table.find_all('th')
            header_text = ' '.join([h.text.strip() for h in headers])
            
            if 'Ticker' in header_text or 'Symbol' in header_text:
                rows = table.find_all('tr')[1:]  # Skip header
                print(f"Found table with {len(rows)} rows")
                
                for row in rows:
                    try:
                        cols = row.find_all('td')
                        if len(cols) >= 2:
                            # Extract ticker (usually first column)
                            ticker_elem = cols[0]
                            ticker = ticker_elem.text.strip()
                            
                            # Extract company name (usually second column)
                            name_elem = cols[1]
                            name = name_elem.text.strip()
                            
                            if ticker and name:
                                companies.append({
                                    "ticker": ticker,
                                    "name": name
                                })
                    except Exception as e:
                        continue
                
                break  # Found the right table
        
        print(f"\nFetched {len(companies)} NASDAQ 100 companies")
        return companies
        
    except Exception as e:
        print(f"Error fetching from Wikipedia: {e}")
        return []


def save_nasdaq100_list(companies):
    """Save NASDAQ 100 list to JSON file"""
    data_dir = Path(__file__).parent.parent / "app" / "data"
    data_dir.mkdir(exist_ok=True)
    
    data = {
        "companies": sorted(companies, key=lambda x: x['ticker']),
        "count": len(companies),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Wikipedia"
    }
    
    json_path = data_dir / "nasdaq100_companies.json"
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\nSaved to: {json_path}")
    
    # Show sample
    print("\nSample companies:")
    for company in companies[:10]:
        print(f"  {company['ticker']}: {company['name']}")
    print("  ...")


def update_database():
    """Update database with NASDAQ 100 flags"""
    from sqlalchemy.orm import Session
    from app.core.database import SessionLocal
    from app.models import Company
    
    print("\nUpdating database with NASDAQ 100 flags...")
    
    # Load the JSON file
    data_dir = Path(__file__).parent.parent / "app" / "data"
    json_path = data_dir / "nasdaq100_companies.json"
    
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    nasdaq100_tickers = {company['ticker'] for company in data['companies']}
    
    db: Session = SessionLocal()
    try:
        # Reset all NASDAQ 100 flags first
        db.query(Company).update({"is_nasdaq100": False})
        
        # Set NASDAQ 100 flags for matching companies
        updated = 0
        for ticker in nasdaq100_tickers:
            company = db.query(Company).filter(Company.ticker == ticker).first()
            if company:
                company.is_nasdaq100 = True
                updated += 1
                print(f"  Updated {ticker}")
        
        db.commit()
        print(f"\n✅ Updated {updated} companies as NASDAQ 100 members")
        
        # Show companies that are in both indices
        both_indices = db.query(Company).filter(
            Company.is_sp500 == True,
            Company.is_nasdaq100 == True
        ).all()
        
        print(f"\nCompanies in both S&P 500 and NASDAQ 100: {len(both_indices)}")
        for company in both_indices[:5]:
            print(f"  {company.ticker}: {company.name}")
        if len(both_indices) > 5:
            print(f"  ... and {len(both_indices) - 5} more")
            
    finally:
        db.close()


def main():
    """Main function"""
    print("NASDAQ 100 Company List Fetcher")
    print("=" * 50)
    
    # Fetch from Wikipedia
    companies = fetch_nasdaq100_from_wikipedia()
    
    if companies:
        save_nasdaq100_list(companies)
        
        # Update database
        try:
            update_database()
        except Exception as e:
            print(f"\nError updating database: {e}")
            print("You may need to run this after setting up the database")
    else:
        print("\nFailed to fetch NASDAQ 100 list")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
#!/usr/bin/env python3
"""
Fetch current NASDAQ 100 companies list with real CIKs from SEC
ENHANCED: Automatically fetches CIKs from SEC Edgar API
"""
import json
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
import sys
from pathlib import Path
import time

sys.path.append(str(Path(__file__).parent.parent))


def fetch_cik_from_sec(ticker: str) -> str:
    """
    Fetch CIK from SEC Edgar API using ticker symbol
    
    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL')
        
    Returns:
        10-digit CIK string, or None if not found
    """
    try:
        # SEC Company Tickers JSON endpoint
        url = "https://www.sec.gov/files/company_tickers.json"
        headers = {
            'User-Agent': 'YourCompany contact@example.com',  # SEC requires identification
            'Accept-Encoding': 'gzip, deflate',
            'Host': 'www.sec.gov'
        }
        
        response = httpx.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        companies = response.json()
        
        # Search for the ticker
        for key, company in companies.items():
            if company.get('ticker', '').upper() == ticker.upper():
                cik_number = company.get('cik_str')
                if cik_number:
                    # Pad to 10 digits
                    return str(cik_number).zfill(10)
        
        return None
        
    except Exception as e:
        print(f"  ⚠️ Error fetching CIK for {ticker}: {e}")
        return None


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
            headers_row = table.find_all('th')
            header_text = ' '.join([h.text.strip() for h in headers_row])
            
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
                                    "name": name,
                                    "cik": None  # Will be fetched later
                                })
                    except Exception as e:
                        continue
                
                break  # Found the right table
        
        print(f"\nFetched {len(companies)} NASDAQ 100 companies from Wikipedia")
        return companies
        
    except Exception as e:
        print(f"Error fetching from Wikipedia: {e}")
        return []


def enrich_with_ciks(companies):
    """Fetch CIKs from SEC for all companies"""
    print("\nFetching CIKs from SEC Edgar API...")
    print("(This may take a few minutes)")
    
    enriched = []
    failed = []
    
    for i, company in enumerate(companies):
        ticker = company['ticker']
        print(f"[{i+1}/{len(companies)}] Fetching CIK for {ticker}...", end=' ')
        
        cik = fetch_cik_from_sec(ticker)
        
        if cik:
            company['cik'] = cik
            enriched.append(company)
            print(f"✅ {cik}")
        else:
            failed.append(ticker)
            print(f"❌ Not found")
        
        # Rate limiting - be nice to SEC
        if (i + 1) % 10 == 0:
            print("  (Pausing to respect rate limits...)")
            time.sleep(1)
    
    print(f"\n✅ Successfully fetched CIKs: {len(enriched)}/{len(companies)}")
    
    if failed:
        print(f"\n⚠️ Failed to fetch CIKs for {len(failed)} companies:")
        for ticker in failed:
            print(f"  - {ticker}")
        print("\nThese companies will be skipped in monitoring.")
    
    return enriched


def save_nasdaq100_list(companies):
    """Save NASDAQ 100 list to JSON file"""
    data_dir = Path(__file__).parent.parent / "app" / "data"
    data_dir.mkdir(exist_ok=True)
    
    # Only include companies with valid CIKs
    valid_companies = [c for c in companies if c.get('cik') and c['cik'] != '0000000000']
    
    data = {
        "companies": sorted(valid_companies, key=lambda x: x['ticker']),
        "count": len(valid_companies),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Wikipedia + SEC Edgar API"
    }
    
    json_path = data_dir / "nasdaq100_companies.json"
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n✅ Saved {len(valid_companies)} companies to: {json_path}")
    
    # Show sample with CIKs
    print("\nSample companies:")
    for company in valid_companies[:10]:
        print(f"  {company['ticker']}: {company['name']} (CIK: {company['cik']})")
    print("  ...")


def update_database(companies):
    """Update database with NASDAQ 100 flags and CIKs"""
    from sqlalchemy.orm import Session
    from app.core.database import SessionLocal
    from app.models.company import Company
    
    print("\nUpdating database with NASDAQ 100 data...")
    
    nasdaq100_tickers = {c['ticker']: c for c in companies if c.get('cik')}
    
    db: Session = SessionLocal()
    try:
        # Reset all NASDAQ 100 flags first
        db.query(Company).update({"is_nasdaq100": False})
        
        # Update or create companies
        updated = 0
        created = 0
        
        for ticker, data in nasdaq100_tickers.items():
            company = db.query(Company).filter(Company.ticker == ticker).first()
            
            if company:
                # Update existing company
                company.is_nasdaq100 = True
                # Update CIK if it was a placeholder
                if not company.cik or company.cik.startswith('N') or company.cik == '0000000000':
                    company.cik = data['cik']
                    print(f"  ✅ Updated {ticker} (CIK: {data['cik']})")
                else:
                    print(f"  ✅ Updated {ticker} (kept existing CIK)")
                updated += 1
            else:
                # Create new company
                company = Company(
                    ticker=ticker,
                    name=data['name'],
                    cik=data['cik'],
                    is_nasdaq100=True,
                    is_sp500=False,
                    is_active=True
                )
                db.add(company)
                print(f"  ➕ Created {ticker} (CIK: {data['cik']})")
                created += 1
        
        db.commit()
        
        print(f"\n✅ Database update complete:")
        print(f"   - Updated: {updated} companies")
        print(f"   - Created: {created} companies")
        
        # Show statistics
        both_indices = db.query(Company).filter(
            Company.is_sp500 == True,
            Company.is_nasdaq100 == True
        ).count()
        
        nasdaq_only = db.query(Company).filter(
            Company.is_nasdaq100 == True,
            Company.is_sp500 == False
        ).count()
        
        print(f"\n📊 Statistics:")
        print(f"   - In both S&P 500 and NASDAQ 100: {both_indices}")
        print(f"   - NASDAQ 100 only: {nasdaq_only}")
        print(f"   - Total NASDAQ 100: {both_indices + nasdaq_only}")
        
    except Exception as e:
        print(f"\n❌ Error updating database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def main():
    """Main function"""
    print("=" * 70)
    print("NASDAQ 100 Company List Fetcher (Enhanced with CIK lookup)")
    print("=" * 70)
    print()
    
    # Step 1: Fetch from Wikipedia
    companies = fetch_nasdaq100_from_wikipedia()
    
    if not companies:
        print("\n❌ Failed to fetch NASDAQ 100 list from Wikipedia")
        return 1
    
    # Step 2: Enrich with CIKs from SEC
    enriched_companies = enrich_with_ciks(companies)
    
    if not enriched_companies:
        print("\n❌ Failed to fetch any CIKs from SEC")
        return 1
    
    # Step 3: Save to JSON
    save_nasdaq100_list(enriched_companies)
    
    # Step 4: Update database
    try:
        update_database(enriched_companies)
    except Exception as e:
        print(f"\n❌ Database update failed: {e}")
        print("The JSON file was saved, but database update failed.")
        return 1
    
    print("\n" + "=" * 70)
    print("✅ All done! NASDAQ 100 companies updated successfully.")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    exit(main())
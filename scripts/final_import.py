#!/usr/bin/env python3
"""
Final import script that handles duplicate CIKs intelligently
"""
import json
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models import Company
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_json_data():
    """Load S&P 500 and NASDAQ 100 data"""
    data_dir = Path(__file__).parent.parent / "app" / "data"
    
    with open(data_dir / "sp500_companies.json", 'r') as f:
        sp500_data = json.load(f)
    
    try:
        with open(data_dir / "nasdaq100_companies.json", 'r') as f:
            nasdaq100_data = json.load(f)
    except:
        nasdaq100_data = {"companies": []}
    
    return sp500_data, nasdaq100_data


def main():
    # Load data
    sp500_data, nasdaq100_data = load_json_data()
    sp500_tickers = {c['ticker']: c for c in sp500_data['companies']}
    nasdaq100_tickers = {c['ticker'] for c in nasdaq100_data['companies']}
    
    logger.info(f"Processing {len(sp500_tickers)} S&P 500 + {len(nasdaq100_tickers)} NASDAQ 100 companies")
    
    db: Session = SessionLocal()
    
    try:
        # Get existing companies
        existing = {c.ticker: c for c in db.query(Company).all()}
        used_ciks = set()
        
        # Collect used CIKs
        for company in existing.values():
            if company.cik and company.cik != '0000000000' and not company.cik.startswith('MOD_'):
                used_ciks.add(company.cik)
        
        logger.info(f"Found {len(existing)} existing companies")
        
        created = 0
        updated = 0
        skipped = 0
        
        # Process each company
        for ticker, sp500_company in sp500_tickers.items():
            cik = sp500_company.get('cik', '0000000000')
            
            if ticker in existing:
                # Update existing company
                company = existing[ticker]
                company.is_sp500 = True
                company.is_nasdaq100 = ticker in nasdaq100_tickers
                company.update_indices()
                updated += 1
                
            else:
                # Check for CIK conflict
                if cik in used_ciks and cik != '0000000000':
                    # Use modified CIK - keep it short
                    new_cik = f"D{ticker[:8]}"  # Max 10 chars
                    logger.warning(f"{ticker}: CIK {cik} already used, using {new_cik}")
                    cik = new_cik
                
                # Create new company
                company = Company(
                    ticker=ticker,
                    name=sp500_company['name'],
                    cik=cik,
                    is_sp500=True,
                    is_nasdaq100=ticker in nasdaq100_tickers,
                    is_active=True
                )
                company.update_indices()
                db.add(company)
                db.flush()  # Make it available immediately
                
                # Track this CIK as used
                if cik and cik != '0000000000':
                    used_ciks.add(cik)
                
                created += 1
                
                # Commit periodically
                if created % 50 == 0:
                    db.commit()
                    logger.info(f"Progress: {created} created, {updated} updated")
        
        # Process NASDAQ-only companies
        nasdaq_only = nasdaq100_tickers - sp500_tickers.keys()
        nasdaq_counter = 1
        for ticker in nasdaq_only:
            if ticker not in existing:
                nasdaq_company = next((c for c in nasdaq100_data['companies'] if c['ticker'] == ticker), None)
                if nasdaq_company:
                    # Use unique CIK for NASDAQ-only companies
                    unique_cik = f"N{nasdaq_counter:09d}"
                    nasdaq_counter += 1
                    
                    company = Company(
                        ticker=ticker,
                        name=nasdaq_company['name'],
                        cik=unique_cik,  # Unique CIK instead of 0000000000
                        is_sp500=False,
                        is_nasdaq100=True,
                        is_active=True
                    )
                    company.update_indices()
                    db.add(company)
                    created += 1
            else:
                company = existing[ticker]
                company.is_nasdaq100 = True
                company.update_indices()
                updated += 1
        
        # Final commit
        db.commit()
        
        # Statistics
        total = db.query(Company).count()
        sp500_count = db.query(Company).filter(Company.is_sp500 == True).count()
        nasdaq_count = db.query(Company).filter(Company.is_nasdaq100 == True).count()
        both = db.query(Company).filter(Company.is_sp500 == True, Company.is_nasdaq100 == True).count()
        
        logger.info("=" * 60)
        logger.info(f"✅ IMPORT COMPLETE!")
        logger.info(f"   Created: {created}")
        logger.info(f"   Updated: {updated}")
        logger.info(f"   Total companies: {total}")
        logger.info(f"   S&P 500: {sp500_count}")
        logger.info(f"   NASDAQ 100: {nasdaq_count}")
        logger.info(f"   Both indices: {both}")
        logger.info("=" * 60)
        
        # Show some examples
        examples = db.query(Company).filter(
            Company.indices.isnot(None)
        ).order_by(Company.ticker).limit(15).all()
        
        logger.info("\nSample companies:")
        for c in examples:
            logger.info(f"   {c.ticker}: {c.indices}")
            
    except Exception as e:
        logger.error(f"Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
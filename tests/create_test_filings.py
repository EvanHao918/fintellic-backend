#!/usr/bin/env python3
"""
Create test filings for all types (10-K, 10-Q, 8-K, S-1)
This helps us test the differentiated processing
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.append(str(Path(__file__).parent))

from app.core.database import SessionLocal
from app.models.company import Company
from app.models.filing import Filing, FilingType, ProcessingStatus


def create_test_filings():
    """Create test filings of each type"""
    print("Creating test filings...")
    
    db = SessionLocal()
    
    try:
        # Test companies data
        test_companies = [
            {
                "cik": "0000320193",
                "ticker": "AAPL",
                "name": "Apple Inc.",
                "filings": [
                    {
                        "type": FilingType.FORM_10K,
                        "accession": "0000320193-24-000123",
                        "date": datetime.now() - timedelta(days=30)
                    },
                    {
                        "type": FilingType.FORM_10Q,
                        "accession": "0000320193-24-000456",
                        "date": datetime.now() - timedelta(days=10)
                    }
                ]
            },
            {
                "cik": "0000789019",
                "ticker": "MSFT",
                "name": "Microsoft Corporation",
                "filings": [
                    {
                        "type": FilingType.FORM_10K,
                        "accession": "0000789019-24-000789",
                        "date": datetime.now() - timedelta(days=45)
                    }
                ]
            },
            {
                "cik": "0001234567",
                "ticker": "RDDT",
                "name": "Reddit Inc.",
                "filings": [
                    {
                        "type": FilingType.FORM_S1,
                        "accession": "0001234567-24-000111",
                        "date": datetime.now() - timedelta(days=5)
                    }
                ]
            }
        ]
        
        # Create companies and filings
        for company_data in test_companies:
            # Check if company exists
            company = db.query(Company).filter(
                Company.cik == company_data["cik"]
            ).first()
            
            if not company:
                print(f"Creating company: {company_data['ticker']}")
                company = Company(
                    cik=company_data["cik"],
                    ticker=company_data["ticker"],
                    name=company_data["name"],
                    legal_name=company_data["name"],
                    is_active=True,
                    is_sp500=company_data["ticker"] in ["AAPL", "MSFT"]
                )
                db.add(company)
                db.flush()
            
            # Create filings
            for filing_data in company_data["filings"]:
                # Check if filing exists
                existing = db.query(Filing).filter(
                    Filing.accession_number == filing_data["accession"]
                ).first()
                
                if not existing:
                    print(f"  Creating {filing_data['type'].value} filing for {company.ticker}")
                    filing = Filing(
                        company_id=company.id,
                        accession_number=filing_data["accession"],
                        filing_type=filing_data["type"],
                        filing_date=filing_data["date"],
                        primary_doc_url=f"https://www.sec.gov/Archives/edgar/data/{company.cik}/{filing_data['accession'].replace('-', '')}/index.htm",
                        status=ProcessingStatus.PENDING
                    )
                    db.add(filing)
        
        db.commit()
        
        # Show summary
        print("\nCurrent filing counts:")
        for filing_type in FilingType:
            count = db.query(Filing).filter(
                Filing.filing_type == filing_type
            ).count()
            print(f"  {filing_type.value}: {count}")
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_test_filings()
# add_test_companies.py
"""
Add test companies to database
"""
from app.core.database import SessionLocal
from app.models.company import Company
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_test_companies():
    """Add major tech companies for testing"""
    db = SessionLocal()
    
    companies_data = [
        {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193"},
        {"ticker": "MSFT", "name": "Microsoft Corporation", "cik": "0000789019"},
        {"ticker": "GOOGL", "name": "Alphabet Inc.", "cik": "0001652044"},
        {"ticker": "AMZN", "name": "Amazon.com Inc.", "cik": "0001018724"},
        {"ticker": "NVDA", "name": "NVIDIA Corporation", "cik": "0001045810"},
        {"ticker": "META", "name": "Meta Platforms Inc.", "cik": "0001326801"},
        {"ticker": "TSLA", "name": "Tesla Inc.", "cik": "0001318605"},
        {"ticker": "BRK.B", "name": "Berkshire Hathaway Inc.", "cik": "0001067983"},
        {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "cik": "0000019617"},
        {"ticker": "UNH", "name": "UnitedHealth Group Inc.", "cik": "0000731766"}
    ]
    
    try:
        added_count = 0
        
        for company_data in companies_data:
            # Check if exists
            existing = db.query(Company).filter(
                Company.ticker == company_data["ticker"]
            ).first()
            
            if not existing:
                company = Company(
                    ticker=company_data["ticker"],
                    name=company_data["name"],
                    cik=company_data["cik"],
                    is_sp500=True,
                    is_active=True
                )
                db.add(company)
                added_count += 1
                logger.info(f"Added: {company_data['ticker']} - {company_data['name']}")
            else:
                logger.info(f"Already exists: {company_data['ticker']}")
        
        db.commit()
        logger.info(f"\n✅ Added {added_count} new companies")
        
        # Show total
        total = db.query(Company).count()
        logger.info(f"Total companies in database: {total}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    add_test_companies()
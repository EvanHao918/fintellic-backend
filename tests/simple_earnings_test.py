# simple_earnings_test.py
"""
Simple test to insert one earnings record
"""
from app.core.database import SessionLocal
from app.models.company import Company
from app.models.earnings_calendar import EarningsCalendar, EarningsTime
from datetime import date
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_single_earnings():
    """Test inserting a single earnings record"""
    db = SessionLocal()
    
    try:
        # Get AAPL
        aapl = db.query(Company).filter(Company.ticker == "AAPL").first()
        if not aapl:
            logger.error("AAPL not found")
            return
            
        logger.info(f"Found {aapl.name} (ID: {aapl.id})")
        
        # Create one earnings record
        earnings = EarningsCalendar(
            company_id=aapl.id,
            earnings_date=date(2025, 7, 15),
            earnings_time=EarningsTime.BMO,  # Using enum directly
            fiscal_quarter="Q3 2025",
            fiscal_year=2025,
            eps_estimate=3.50,
            revenue_estimate=85000.0,
            is_confirmed=True,
            source="test"
        )
        
        db.add(earnings)
        logger.info("Added earnings record, committing...")
        
        db.commit()
        logger.info("✅ Success! Earnings record created")
        
        # Verify
        count = db.query(EarningsCalendar).count()
        logger.info(f"Total earnings records: {count}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_single_earnings()
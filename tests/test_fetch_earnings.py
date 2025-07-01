# test_fetch_earnings.py
"""
Test script to fetch and store earnings data for AAPL
"""
from app.core.database import SessionLocal
from app.models.company import Company
from app.services.earnings_calendar_service import EarningsCalendarService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_fetch_earnings():
    """Test fetching earnings data for AAPL"""
    db = SessionLocal()
    
    try:
        # Get AAPL company
        aapl = db.query(Company).filter(Company.ticker == "AAPL").first()
        
        if not aapl:
            logger.error("AAPL not found in database")
            return
        
        logger.info(f"Found {aapl.name} (ID: {aapl.id})")
        
        # Fetch earnings data from yfinance
        logger.info("Fetching earnings data from yfinance...")
        earnings_data = EarningsCalendarService.fetch_earnings_calendar("AAPL")
        
        if earnings_data:
            logger.info(f"Found {len(earnings_data)} upcoming earnings dates:")
            for earning in earnings_data[:3]:  # Show first 3
                logger.info(f"  - {earning['earnings_date']} ({earning['earnings_time']})")
                logger.info(f"    Fiscal: {earning['fiscal_quarter']}")
                logger.info(f"    EPS Est: {earning['eps_estimate']}")
        else:
            logger.warning("No earnings data found")
        
        # Update in database
        logger.info("\nUpdating database...")
        updated = EarningsCalendarService.update_company_earnings(db, aapl)
        logger.info(f"Updated {len(updated)} earnings entries in database")
        
        # Verify by querying
        from app.models.earnings_calendar import EarningsCalendar
        db_earnings = db.query(EarningsCalendar).filter(
            EarningsCalendar.company_id == aapl.id
        ).all()
        
        logger.info(f"\nDatabase now contains {len(db_earnings)} earnings entries for AAPL")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_fetch_earnings()
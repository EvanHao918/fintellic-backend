# create_mock_earnings.py
"""
Create mock earnings calendar data for testing
"""
from datetime import date, timedelta
from app.core.database import SessionLocal
from app.models.company import Company
from app.models.earnings_calendar import EarningsCalendar, EarningsTime
import random
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_mock_earnings():
    """Create mock earnings data for top companies"""
    db = SessionLocal()
    
    try:
        # Get some top companies
        companies = db.query(Company).filter(
            Company.ticker.in_(['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK.B', 'JPM', 'UNH'])
        ).all()
        
        if not companies:
            logger.error("No companies found. Please run add_test_data.py first")
            return
        
        logger.info(f"Creating mock earnings for {len(companies)} companies")
        
        created_count = 0
        
        for company in companies:
            # Create 4 quarters of earnings
            base_date = date.today()
            
            for quarter in range(4):
                # Calculate earnings date (roughly every 3 months)
                earnings_date = base_date + timedelta(days=90 * quarter + random.randint(-10, 10))
                
                # Skip if in the past
                if earnings_date < date.today():
                    continue
                
                # Check if already exists
                existing = db.query(EarningsCalendar).filter(
                    EarningsCalendar.company_id == company.id,
                    EarningsCalendar.earnings_date == earnings_date
                ).first()
                
                if existing:
                    continue
                
                # Determine time
                time_choice = random.choice([EarningsTime.BMO, EarningsTime.AMC, EarningsTime.AMC])
                
                # Create mock estimates
                fiscal_quarter = f"Q{((earnings_date.month - 1) // 3) + 1} {earnings_date.year}"
                
                # Create earnings entry
                earnings = EarningsCalendar(
                    company_id=company.id,
                    earnings_date=earnings_date,
                    earnings_time=time_choice,
                    fiscal_quarter=fiscal_quarter,
                    fiscal_year=earnings_date.year,
                    eps_estimate=round(random.uniform(1.0, 5.0), 2),
                    revenue_estimate=round(random.uniform(10000, 100000), 0),  # In millions
                    previous_eps=round(random.uniform(0.8, 4.5), 2),
                    previous_revenue=round(random.uniform(9000, 95000), 0),
                    is_confirmed=random.choice([True, False]),
                    source="mock_data"
                )
                
                db.add(earnings)
                created_count += 1
                
                logger.info(f"  {company.ticker}: {earnings_date} ({time_choice.value}) - {fiscal_quarter}")
        
        db.commit()
        logger.info(f"\n✅ Created {created_count} earnings entries")
        
        # Verify
        total_earnings = db.query(EarningsCalendar).count()
        logger.info(f"Total earnings in database: {total_earnings}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    create_mock_earnings()
# fix_mock_earnings.py
"""
Fixed script to create mock earnings calendar data
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
    """Create mock earnings data for all companies"""
    db = SessionLocal()
    
    try:
        # Get ALL companies in the database
        companies = db.query(Company).all()
        
        if not companies:
            logger.error("No companies found in database!")
            return
        
        logger.info(f"Creating mock earnings for {len(companies)} companies")
        
        created_count = 0
        
        for company in companies:
            logger.info(f"\nProcessing {company.ticker} (ID: {company.id})")
            
            # Create earnings for next 4 quarters
            base_date = date.today()
            
            # Start from next month to ensure future dates
            next_month = base_date.replace(day=1) + timedelta(days=32)
            next_month = next_month.replace(day=1)
            
            for quarter in range(4):
                # Calculate earnings date (every 3 months, with some randomness)
                earnings_date = next_month + timedelta(days=90 * quarter + random.randint(5, 25))
                
                # Determine time (use lowercase for database)
                time_choice = random.choice([EarningsTime.BMO, EarningsTime.AMC])
                
                # The actual database value needs to match the enum
                db_time_value = time_choice.value  # This should be lowercase
                
                # Create fiscal quarter
                quarter_num = ((earnings_date.month - 1) // 3) + 1
                fiscal_quarter = f"Q{quarter_num} {earnings_date.year}"
                
                # Check if already exists
                existing = db.query(EarningsCalendar).filter(
                    EarningsCalendar.company_id == company.id,
                    EarningsCalendar.earnings_date == earnings_date
                ).first()
                
                if existing:
                    logger.info(f"  Earnings already exists for {earnings_date}")
                    continue
                
                # Create earnings entry
                earnings = EarningsCalendar(
                    company_id=company.id,
                    earnings_date=earnings_date,
                    earnings_time=time_choice,  # Use the enum directly
                    fiscal_quarter=fiscal_quarter,
                    fiscal_year=earnings_date.year,
                    eps_estimate=round(random.uniform(1.0, 5.0), 2),
                    revenue_estimate=round(random.uniform(10000, 100000), 0),
                    previous_eps=round(random.uniform(0.8, 4.5), 2),
                    previous_revenue=round(random.uniform(9000, 95000), 0),
                    is_confirmed=quarter == 0,  # First quarter is confirmed
                    source="mock_data"
                )
                
                db.add(earnings)
                created_count += 1
                
                logger.info(f"  Created: {earnings_date} ({time_choice.value}) - {fiscal_quarter}")
        
        db.commit()
        logger.info(f"\n✅ Created {created_count} earnings entries")
        
        # Verify
        total_earnings = db.query(EarningsCalendar).count()
        future_earnings = db.query(EarningsCalendar).filter(
            EarningsCalendar.earnings_date >= date.today()
        ).count()
        
        logger.info(f"Total earnings in database: {total_earnings}")
        logger.info(f"Future earnings (from today): {future_earnings}")
        
        # Show next 5 upcoming earnings
        upcoming = db.query(EarningsCalendar).join(Company).filter(
            EarningsCalendar.earnings_date >= date.today()
        ).order_by(EarningsCalendar.earnings_date).limit(5).all()
        
        logger.info("\nNext 5 upcoming earnings:")
        for e in upcoming:
            logger.info(f"  {e.company.ticker}: {e.earnings_date} ({e.earnings_time.value})")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    create_mock_earnings()
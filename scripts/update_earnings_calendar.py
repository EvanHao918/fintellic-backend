#!/usr/bin/env python3
"""
Manual script to update earnings calendar
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.earnings_calendar_service import EarningsCalendarService
from app.core.database import SessionLocal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Update earnings calendar for all S&P 500 companies"""
    logger.info("Starting manual earnings calendar update...")
    
    db = SessionLocal()
    try:
        # Import fmp_service to ensure proper cleanup
        from app.services.fmp_service import fmp_service
        
        updated_count = await EarningsCalendarService.update_all_sp500_earnings(db)
        logger.info(f"✅ Successfully updated {updated_count} earnings entries")
        
        # Close FMP service session
        await fmp_service.close()
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
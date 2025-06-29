#!/usr/bin/env python3
"""
Fintellic Main Scheduler
Runs the filing discovery and processing pipeline continuously
"""
import asyncio
import sys
import signal
import logging
from datetime import datetime
from pathlib import Path
from sqlalchemy import text  # Added for SQL query

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.scheduler import filing_scheduler
from app.services.edgar_scanner import edgar_scanner
from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/scheduler.log')
    ]
)

logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_flag = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global shutdown_flag
    logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
    shutdown_flag = True


async def check_system_health():
    """Check if all required services are running"""
    try:
        # Check database connection
        db = SessionLocal()
        db.execute(text("SELECT 1"))  # Fixed: wrapped in text()
        db.close()
        logger.info("✅ Database connection OK")
        
        # Check Redis (for Celery)
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        logger.info("✅ Redis connection OK")
        
        # Check if we have S&P 500 companies loaded
        stats = await edgar_scanner.get_sp500_stats()
        if stats['total_sp500_companies'] > 0:
            logger.info(f"✅ Loaded {stats['total_sp500_companies']} S&P 500 companies")
        else:
            logger.error("❌ No S&P 500 companies loaded!")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"❌ System health check failed: {e}")
        return False


async def display_statistics():
    """Display current system statistics"""
    try:
        db = SessionLocal()
        
        # Count filings by status
        total_filings = db.query(Filing).count()
        pending = db.query(Filing).filter(Filing.status == ProcessingStatus.PENDING).count()
        processing = db.query(Filing).filter(Filing.status == ProcessingStatus.DOWNLOADING).count()
        processing += db.query(Filing).filter(Filing.status == ProcessingStatus.PARSING).count()
        processing += db.query(Filing).filter(Filing.status == ProcessingStatus.AI_PROCESSING).count()
        completed = db.query(Filing).filter(Filing.status == ProcessingStatus.COMPLETED).count()
        failed = db.query(Filing).filter(Filing.status == ProcessingStatus.FAILED).count()
        
        logger.info("📊 System Statistics:")
        logger.info(f"   Total Filings: {total_filings}")
        logger.info(f"   ⏳ Pending: {pending}")
        logger.info(f"   🔄 Processing: {processing}")
        logger.info(f"   ✅ Completed: {completed}")
        logger.info(f"   ❌ Failed: {failed}")
        
        # Get scheduler status
        scheduler_status = filing_scheduler.get_status()
        logger.info(f"   🔍 Scans performed: {scheduler_status['total_scans']}")
        logger.info(f"   📄 New filings found: {scheduler_status['total_filings_found']}")
        
        db.close()
        
    except Exception as e:
        logger.error(f"Error displaying statistics: {e}")


async def main():
    """Main scheduler loop"""
    logger.info("=" * 60)
    logger.info("🚀 Starting Fintellic Filing Scheduler")
    logger.info(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("   Mode: RSS-based scanning (1-minute intervals)")
    logger.info("=" * 60)
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Check system health
    if not await check_system_health():
        logger.error("System health check failed. Please ensure all services are running:")
        logger.error("  1. PostgreSQL database")
        logger.error("  2. Redis server")
        logger.error("  3. Celery worker")
        sys.exit(1)
    
    # Start the scheduler
    logger.info("\n🔄 Starting continuous filing discovery...")
    await filing_scheduler.start()
    
    # Keep running and display statistics periodically
    stats_counter = 0
    while not shutdown_flag:
        try:
            await asyncio.sleep(60)  # Wait 1 minute
            
            stats_counter += 1
            # Display statistics every 5 minutes
            if stats_counter >= 5:
                await display_statistics()
                stats_counter = 0
                
            # Quick status update every minute
            else:
                status = filing_scheduler.get_status()
                logger.info(f"⏱️  Scheduler running... Scans: {status['total_scans']}, "
                          f"Filings found: {status['total_filings_found']}")
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            await asyncio.sleep(60)
    
    # Graceful shutdown
    logger.info("\n🛑 Shutting down scheduler...")
    await filing_scheduler.stop()
    
    # Final statistics
    await display_statistics()
    
    logger.info("✅ Scheduler stopped successfully")
    logger.info("=" * 60)


if __name__ == "__main__":
    # Create logs directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nScheduler interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
import asyncio
import logging
from datetime import datetime, time
from typing import Optional, Dict
from app.services.edgar_scanner import edgar_scanner
from app.services.earnings_calendar_service import EarningsCalendarService
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


class FilingScheduler:
    """
    Manages scheduled tasks for filing discovery and earnings calendar updates
    Optimized for RSS-based scanning (every 1 minute) and daily calendar updates
    """
    
    def __init__(self):
        self.scan_interval = 60  # 1 minute in seconds (RSS is efficient)
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
        self.scan_count = 0
        self.filings_found = 0
        self.last_calendar_update = None
        self.calendar_update_hour = 6  # Update calendar at 6 AM daily
        
    async def start(self):
        """Start the scheduler"""
        if self.is_running:
            logger.warning("Scheduler is already running")
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._run_scheduler())
        logger.info("Filing scheduler started (RSS mode - 1 minute intervals)")
        
    async def stop(self):
        """Stop the scheduler"""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info(f"Filing scheduler stopped. Total scans: {self.scan_count}, Filings found: {self.filings_found}")
        
    async def _run_scheduler(self):
        """Main scheduler loop - optimized for RSS and daily tasks"""
        logger.info("RSS-based scheduler loop started")
        
        # Run initial scan immediately
        await self._perform_scan()
        
        # Check if we need to update earnings calendar on startup
        await self._check_and_update_earnings_calendar()
        
        while self.is_running:
            try:
                # Wait for next scan
                await asyncio.sleep(self.scan_interval)
                
                # Perform scheduled scan
                await self._perform_scan()
                
                # Check for daily tasks every hour
                current_time = datetime.now()
                if current_time.minute < 2:  # Within first 2 minutes of the hour
                    await self._check_and_update_earnings_calendar()
                
            except asyncio.CancelledError:
                logger.info("Scheduler loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in scheduler: {e}", exc_info=True)
                # Continue running even if there's an error
                await asyncio.sleep(self.scan_interval)
    
    async def _perform_scan(self):
        """Perform a single scan"""
        self.scan_count += 1
        scan_start = datetime.now()
        
        logger.info(f"Starting scheduled scan #{self.scan_count} at {scan_start.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # Run the scanner
            new_filings = await edgar_scanner.scan_for_new_filings()
            
            # Update statistics
            self.filings_found += len(new_filings)
            
            # Log results
            scan_duration = (datetime.now() - scan_start).total_seconds()
            
            if new_filings:
                logger.info(
                    f"Scan #{self.scan_count} completed in {scan_duration:.2f}s. "
                    f"Found {len(new_filings)} new filings! Total found: {self.filings_found}"
                )
                
                # Log each new filing
                for filing in new_filings:
                    logger.info(
                        f"  → {filing['ticker']} {filing['form_type']} "
                        f"({filing['filing_date']}) via {filing.get('discovery_method', 'RSS')}"
                    )
            else:
                logger.debug(
                    f"Scan #{self.scan_count} completed in {scan_duration:.2f}s. "
                    f"No new filings found."
                )
                
        except Exception as e:
            logger.error(f"Error during scan #{self.scan_count}: {e}", exc_info=True)
    
    async def _check_and_update_earnings_calendar(self):
        """Check if it's time to update earnings calendar"""
        current_time = datetime.now()
        
        # Check if we should update (once per day at specified hour)
        should_update = False
        
        if self.last_calendar_update is None:
            # Never updated, do it now
            should_update = True
        elif current_time.hour == self.calendar_update_hour:
            # Check if we haven't updated today
            if self.last_calendar_update.date() < current_time.date():
                should_update = True
        
        if should_update:
            await self._update_earnings_calendar()
    
    async def _update_earnings_calendar(self):
        """Update earnings calendar for all S&P 500 companies"""
        logger.info("🗓️  Starting daily earnings calendar update...")
        update_start = datetime.now()
        
        db = SessionLocal()
        try:
            # Update all S&P 500 earnings
            updated_count = await EarningsCalendarService.update_all_sp500_earnings(db)
            
            # Update timestamp
            self.last_calendar_update = datetime.now()
            
            # Log results
            duration = (datetime.now() - update_start).total_seconds()
            logger.info(
                f"✅ Earnings calendar update completed in {duration:.2f}s. "
                f"Updated {updated_count} entries."
            )
            
        except Exception as e:
            logger.error(f"❌ Error updating earnings calendar: {e}", exc_info=True)
        finally:
            db.close()
    
    async def run_single_scan(self):
        """Run a single scan immediately (for testing)"""
        logger.info("Running manual scan...")
        
        try:
            scan_start = datetime.now()
            new_filings = await edgar_scanner.scan_for_new_filings()
            scan_duration = (datetime.now() - scan_start).total_seconds()
            
            logger.info(
                f"Manual scan completed in {scan_duration:.2f}s. "
                f"Found {len(new_filings)} new filings"
            )
            
            return new_filings
            
        except Exception as e:
            logger.error(f"Error during manual scan: {e}", exc_info=True)
            return []
    
    async def update_earnings_calendar_now(self):
        """Manually trigger earnings calendar update"""
        logger.info("Manually triggering earnings calendar update...")
        await self._update_earnings_calendar()
    
    def get_status(self) -> Dict:
        """Get scheduler status"""
        return {
            "is_running": self.is_running,
            "scan_interval_seconds": self.scan_interval,
            "total_scans": self.scan_count,
            "total_filings_found": self.filings_found,
            "mode": "RSS (Efficient)",
            "last_calendar_update": self.last_calendar_update.isoformat() if self.last_calendar_update else None,
            "calendar_update_hour": self.calendar_update_hour
        }


# Create singleton instance
filing_scheduler = FilingScheduler()
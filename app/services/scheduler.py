import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict
from app.services.edgar_scanner import edgar_scanner

logger = logging.getLogger(__name__)


class FilingScheduler:
    """
    Manages scheduled tasks for filing discovery
    Optimized for RSS-based scanning (every 1 minute)
    """
    
    def __init__(self):
        self.scan_interval = 60  # 1 minute in seconds (RSS is efficient)
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
        self.scan_count = 0
        self.filings_found = 0
        
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
        """Main scheduler loop - optimized for RSS"""
        logger.info("RSS-based scheduler loop started")
        
        # Run initial scan immediately
        await self._perform_scan()
        
        while self.is_running:
            try:
                # Wait for next scan
                await asyncio.sleep(self.scan_interval)
                
                # Perform scheduled scan
                await self._perform_scan()
                
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
    
    def get_status(self) -> Dict:
        """Get scheduler status"""
        return {
            "is_running": self.is_running,
            "scan_interval_seconds": self.scan_interval,
            "total_scans": self.scan_count,
            "total_filings_found": self.filings_found,
            "mode": "RSS (Efficient)"
        }


# Create singleton instance
filing_scheduler = FilingScheduler()
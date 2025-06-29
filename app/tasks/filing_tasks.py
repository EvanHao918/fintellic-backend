# app/tasks/filing_tasks.py
"""
Celery tasks for filing processing
"""
import logging
from typing import Optional
from celery import Task
import asyncio

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
from app.services.filing_downloader import filing_downloader
from app.services.ai_processor import ai_processor

logger = logging.getLogger(__name__)


class FilingTask(Task):
    """Base task with database session management"""
    _db = None

    @property
    def db(self):
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """Clean up database session after task completion"""
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(base=FilingTask, bind=True, max_retries=3)
def process_filing_task(self, filing_id: int):
    """
    Process a single filing through the complete pipeline:
    1. Download documents
    2. Extract text  
    3. Generate AI analysis
    4. Send notifications (future)
    
    Args:
        filing_id: Database ID of the filing to process
    """
    try:
        logger.info(f"Starting processing for filing {filing_id}")
        
        # Get filing from database
        filing = self.db.query(Filing).filter(Filing.id == filing_id).first()
        
        if not filing:
            logger.error(f"Filing {filing_id} not found")
            return {"status": "error", "message": "Filing not found"}
        
        # Create event loop for async operations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Step 1: Download filing documents
            if filing.status == ProcessingStatus.PENDING:
                logger.info(f"Downloading filing {filing.accession_number}")
                
                # Run async download_filing
                success = loop.run_until_complete(
                    filing_downloader.download_filing(self.db, filing)
                )
                
                if not success:
                    raise Exception(f"Failed to download filing {filing.accession_number}")
            
            # Step 2 & 3: AI processing (includes text extraction)
            if filing.status in [ProcessingStatus.PARSING, ProcessingStatus.DOWNLOADING]:
                logger.info(f"Processing filing {filing.accession_number} with AI")
                
                # Run async AI processing
                success = loop.run_until_complete(
                    ai_processor.process_filing(self.db, filing)
                )
                
                if not success:
                    raise Exception(f"Failed to process filing {filing.accession_number} with AI")
        
        finally:
            # Clean up the event loop
            loop.close()
        
        # Step 4: Send notifications (placeholder for future)
        if filing.status == ProcessingStatus.COMPLETED:
            send_filing_notifications.delay(filing_id)
        
        logger.info(f"Successfully processed filing {filing_id}")
        return {
            "status": "success",
            "filing_id": filing_id,
            "company": filing.company.ticker,
            "type": filing.filing_type.value
        }
        
    except Exception as e:
        logger.error(f"Error processing filing {filing_id}: {e}", exc_info=True)
        
        # Update filing status to failed
        filing = self.db.query(Filing).filter(Filing.id == filing_id).first()
        if filing:
            filing.status = ProcessingStatus.FAILED
            filing.error_message = str(e)
            self.db.commit()
        
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@celery_app.task(base=FilingTask)
def process_pending_filings():
    """
    Find and process all pending filings
    This task can be scheduled to run periodically
    """
    try:
        # Get all pending filings
        pending_filings = SessionLocal().query(Filing).filter(
            Filing.status == ProcessingStatus.PENDING
        ).all()
        
        logger.info(f"Found {len(pending_filings)} pending filings")
        
        # Queue each filing for processing
        for filing in pending_filings:
            process_filing_task.delay(filing.id)
        
        return {
            "status": "success",
            "queued": len(pending_filings)
        }
        
    except Exception as e:
        logger.error(f"Error queuing pending filings: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@celery_app.task
def send_filing_notifications(filing_id: int):
    """
    Send push notifications for completed filing
    Placeholder for future notification system
    """
    logger.info(f"Would send notifications for filing {filing_id}")
    # TODO: Implement push notification logic
    # - Get all users watching this company
    # - Send push notifications
    # - Update notification status
    return {"status": "notifications_sent"}
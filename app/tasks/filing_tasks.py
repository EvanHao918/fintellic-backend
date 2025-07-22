# app/tasks/filing_tasks.py
"""
Celery tasks for filing processing
"""
import logging
from typing import Optional
from celery import Task
import asyncio

from app.core.celery_app import celery_app
from app.core.database import SessionLocal, ThreadSafeSession, get_task_db
from app.models.filing import Filing, ProcessingStatus
from app.services.filing_downloader import filing_downloader
from app.services.ai_processor import ai_processor

logger = logging.getLogger(__name__)


class FilingTask(Task):
    """Base task with database session management"""
    
    def get_db(self):
        """Get a thread-safe database session"""
        # 使用线程安全的 session
        return ThreadSafeSession()
    
    def close_db(self, db):
        """Close and clean up the database session"""
        if db:
            db.close()
            ThreadSafeSession.remove()  # 清理线程本地会话


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
    db = None
    try:
        logger.info(f"Starting processing for filing {filing_id}")
        
        # 使用线程安全的数据库会话
        db = self.get_db()
        
        # Get filing from database
        filing = db.query(Filing).filter(Filing.id == filing_id).first()
        
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
                
                # Commit current state before async operation
                db.commit()
                
                # Run async download_filing
                success = loop.run_until_complete(
                    filing_downloader.download_filing(db, filing)
                )
                
                if not success:
                    raise Exception(f"Failed to download filing {filing.accession_number}")
            
            # Step 2 & 3: AI processing (includes text extraction)
            if filing.status in [ProcessingStatus.PARSING, ProcessingStatus.DOWNLOADING]:
                logger.info(f"Processing filing {filing.accession_number} with AI")
                
                # Commit current state before async operation
                db.commit()
                
                # Run async AI processing
                success = loop.run_until_complete(
                    ai_processor.process_filing(db, filing)
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
            "company": filing.company.ticker if filing.company else "Unknown",
            "type": filing.filing_type.value
        }
        
    except Exception as e:
        logger.error(f"Error processing filing {filing_id}: {e}", exc_info=True)
        
        # Update filing status to failed
        if db:
            try:
                filing = db.query(Filing).filter(Filing.id == filing_id).first()
                if filing:
                    filing.status = ProcessingStatus.FAILED
                    filing.error_message = str(e)[:500]  # Limit error message length
                    db.commit()
            except Exception as update_error:
                logger.error(f"Failed to update filing status: {update_error}")
                db.rollback()
        
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
    
    finally:
        # Always clean up the database session
        if db:
            self.close_db(db)


@celery_app.task(base=FilingTask)
def process_pending_filings():
    """
    Find and process all pending filings
    This task can be scheduled to run periodically
    """
    try:
        # 使用上下文管理器确保会话清理
        with get_task_db() as db:
            # Get all pending filings
            pending_filings = db.query(Filing).filter(
                Filing.status == ProcessingStatus.PENDING
            ).limit(50).all()  # 限制批处理数量
            
            logger.info(f"Found {len(pending_filings)} pending filings")
            
            # Queue each filing for processing
            filing_ids = []
            for filing in pending_filings:
                process_filing_task.delay(filing.id)
                filing_ids.append(filing.id)
            
            return {
                "status": "success",
                "queued": len(pending_filings),
                "filing_ids": filing_ids
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
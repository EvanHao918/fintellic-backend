# app/tasks/filing_tasks.py
"""
Celery tasks for filing processing
ENHANCED: Added validation throughout the pipeline
FIXED: Timezone-aware datetime comparisons
FIXED: Added retry logic for "Filing not found" errors
FIXED: Better error handling for AI processing failures
"""
import logging
from typing import Optional, Dict
from celery import Task
import asyncio
from datetime import datetime, timezone
import time
import traceback

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
        return ThreadSafeSession()
    
    def close_db(self, db):
        """Close and clean up the database session"""
        if db:
            db.close()
            ThreadSafeSession.remove()
    
    def validate_filing(self, filing: Filing) -> tuple[bool, str]:
        """
        Validate filing before processing
        FIXED: Use timezone-aware datetime for comparison
        """
        # Check if filing has required fields
        if not filing.accession_number:
            return False, "Missing accession number"
        
        if not filing.company_id:
            return False, "Missing company ID"
        
        if not filing.filing_type:
            return False, "Missing filing type"
        
        # FIXED: Use timezone-aware datetime for comparison
        current_time_utc = datetime.now(timezone.utc)
        
        # Handle both naive and aware datetimes
        if filing.filing_date:
            if filing.filing_date.tzinfo is None:
                filing_date_utc = filing.filing_date.replace(tzinfo=timezone.utc)
            else:
                filing_date_utc = filing.filing_date.astimezone(timezone.utc)
            
            if filing_date_utc > current_time_utc:
                return False, f"Filing date {filing_date_utc} is in the future"
        
        # Validate accession number format
        import re
        if not re.match(r'^\d{10}-\d{2}-\d{6}$', filing.accession_number):
            return False, f"Invalid accession number format: {filing.accession_number}"
        
        return True, ""


@celery_app.task(base=FilingTask, bind=True, max_retries=3)
def process_filing_task(self, filing_id: int):
    """
    Process a single filing through the complete pipeline
    ENHANCED: Added validation at each step
    FIXED: Added retry logic for "Filing not found" errors
    FIXED: Better error handling for AI processing
    """
    db = None
    filing = None
    
    try:
        logger.info(f"Starting processing for filing {filing_id}")
        
        # FIXED: Add retry logic for "Filing not found"
        max_attempts = 3
        for attempt in range(max_attempts):
            db = self.get_db()
            
            # Try to get filing from database
            filing = db.query(Filing).filter(Filing.id == filing_id).first()
            
            if filing:
                break  # Found it!
            
            # Not found, maybe transaction not committed yet
            if attempt < max_attempts - 1:
                logger.warning(f"Filing {filing_id} not found (attempt {attempt + 1}/{max_attempts}), waiting...")
                self.close_db(db)
                db = None
                time.sleep(2)  # Wait 2 seconds before retry
                
        if not filing:
            logger.error(f"Filing {filing_id} not found after {max_attempts} attempts")
            return {"status": "error", "message": "Filing not found"}
        
        # ENHANCED: Validate filing before processing
        is_valid, error_msg = self.validate_filing(filing)
        if not is_valid:
            logger.error(f"Filing {filing_id} validation failed: {error_msg}")
            filing.status = ProcessingStatus.FAILED
            filing.error_message = f"Validation failed: {error_msg}"
            db.commit()
            return {"status": "error", "message": error_msg}
        
        logger.info(f"Processing filing: {filing.company.ticker} - {filing.filing_type.value} ({filing.accession_number})")
        
        # Check if filing has already been successfully processed
        if filing.status == ProcessingStatus.COMPLETED and filing.unified_analysis:
            logger.info(f"Filing {filing_id} already completed with analysis")
            return {
                "status": "success",
                "filing_id": filing_id,
                "company": filing.company.ticker if filing.company else "Unknown",
                "type": filing.filing_type.value,
                "analysis_version": filing.analysis_version,
                "message": "Already processed"
            }
        
        # Create event loop for async operations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Step 1: Download filing documents
            if filing.status in [ProcessingStatus.PENDING, ProcessingStatus.FAILED]:
                logger.info(f"Downloading filing {filing.accession_number}")
                
                # Update status to DOWNLOADING
                filing.status = ProcessingStatus.DOWNLOADING
                filing.processing_started_at = datetime.utcnow()
                db.commit()
                
                # Run async download_filing
                success = loop.run_until_complete(
                    filing_downloader.download_filing(db, filing)
                )
                
                if not success:
                    # Check if specific error is available
                    error_detail = filing.error_message or "Unknown download error"
                    raise Exception(f"Failed to download filing: {error_detail}")
                
                # ENHANCED: Validate downloaded content
                from pathlib import Path
                filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
                if not filing_dir.exists():
                    raise Exception(f"Filing directory not created: {filing_dir}")
                
                # Check if we have any content files
                content_files = list(filing_dir.glob("*.htm")) + list(filing_dir.glob("*.html")) + list(filing_dir.glob("*.txt"))
                if not content_files:
                    raise Exception(f"No content files downloaded for filing {filing.accession_number}")
                
                logger.info(f"Successfully downloaded {len(content_files)} files for {filing.accession_number}")
            
            # Step 2 & 3: AI processing (includes text extraction)
            if filing.status in [ProcessingStatus.PARSING, ProcessingStatus.DOWNLOADING]:
                logger.info(f"Processing filing {filing.accession_number} with AI")
                
                # Check if OpenAI API key is configured
                from app.core.config import settings
                if not settings.OPENAI_API_KEY:
                    raise Exception("OpenAI API key not configured")
                
                # Commit current state before async operation
                db.commit()
                
                # Run async AI processing with better error handling
                try:
                    success = loop.run_until_complete(
                        ai_processor.process_filing(db, filing)
                    )
                    
                    if not success:
                        # Check if there's a specific error message
                        error_detail = filing.error_message or "AI processing returned failure"
                        
                        # Check if it's an API key issue
                        if "api_key" in error_detail.lower() or "unauthorized" in error_detail.lower():
                            raise Exception(f"OpenAI API authentication failed - check API key")
                        elif "rate" in error_detail.lower():
                            raise Exception(f"OpenAI API rate limit exceeded")
                        elif "quota" in error_detail.lower():
                            raise Exception(f"OpenAI API quota exceeded")
                        else:
                            raise Exception(f"AI processing failed: {error_detail}")
                    
                except Exception as ai_error:
                    # Log the full error for debugging
                    logger.error(f"AI processing error details: {ai_error}", exc_info=True)
                    
                    # Get more specific error information
                    error_str = str(ai_error)
                    
                    # Check for common OpenAI errors
                    if "openai" in error_str.lower():
                        if "api" in error_str.lower() and "key" in error_str.lower():
                            raise Exception("OpenAI API key is invalid or not set")
                        elif "rate" in error_str.lower():
                            raise Exception("OpenAI rate limit exceeded - retry later")
                        elif "quota" in error_str.lower():
                            raise Exception("OpenAI quota exceeded - check billing")
                        elif "timeout" in error_str.lower():
                            raise Exception("OpenAI API timeout - filing may be too large")
                        else:
                            raise Exception(f"OpenAI API error: {error_str[:200]}")
                    else:
                        # Re-raise the original error with more context
                        raise Exception(f"AI processing failed: {error_str[:200]}")
                
                # ENHANCED: Validate AI output
                if not filing.unified_analysis or len(filing.unified_analysis) < 100:
                    # Try to get more specific error info
                    if filing.error_message:
                        raise Exception(f"AI processing incomplete: {filing.error_message}")
                    else:
                        raise Exception("AI processing produced insufficient content")
                
                # Check for data source markings (v5 requirement)
                if filing.analysis_version == "v5" and '[DOC:' not in filing.unified_analysis:
                    logger.warning("AI output missing data source markings")
                
                logger.info(f"AI processing completed successfully for {filing.accession_number}")
        
        finally:
            # Clean up the event loop
            loop.close()
        
        # Step 4: Post-processing validation
        if filing.status == ProcessingStatus.COMPLETED:
            # Validate completeness
            validation_results = validate_completed_filing(filing)
            if not validation_results['is_valid']:
                logger.warning(f"Completed filing has issues: {validation_results['issues']}")
            
            # Send notifications
            send_filing_notifications.delay(filing_id)
        
        logger.info(f"✅ Successfully processed filing {filing_id}")
        return {
            "status": "success",
            "filing_id": filing_id,
            "company": filing.company.ticker if filing.company else "Unknown",
            "type": filing.filing_type.value,
            "analysis_version": filing.analysis_version
        }
        
    except Exception as e:
        # Get detailed error information
        error_message = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error processing filing {filing_id}: {error_message}")
        logger.debug(f"Full traceback:\n{error_traceback}")
        
        # Update filing status to failed with detailed error
        if db and filing:
            try:
                filing.status = ProcessingStatus.FAILED
                
                # Store both the error message and important context
                if "OpenAI" in error_message:
                    filing.error_message = f"AI Service Error: {error_message[:500]}"
                elif "download" in error_message.lower():
                    filing.error_message = f"Download Error: {error_message[:500]}"
                else:
                    filing.error_message = error_message[:500]
                
                filing.processing_completed_at = datetime.utcnow()
                db.commit()
                
            except Exception as update_error:
                logger.error(f"Failed to update filing status: {update_error}")
                db.rollback()
        
        # Determine if we should retry
        should_retry = True
        retry_countdown = 60 * (2 ** self.request.retries)  # Exponential backoff
        
        # Don't retry for certain errors
        if "API key" in error_message or "invalid" in error_message.lower():
            should_retry = False
            logger.error("Not retrying - API key issue needs manual fix")
        elif "quota" in error_message.lower():
            should_retry = False
            logger.error("Not retrying - quota exceeded needs manual fix")
        elif self.request.retries >= self.max_retries:
            should_retry = False
            logger.error(f"Max retries ({self.max_retries}) reached")
        
        if should_retry:
            logger.info(f"Will retry in {retry_countdown} seconds (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e, countdown=retry_countdown)
        else:
            # Return error instead of raising to prevent Celery from retrying
            return {
                "status": "error",
                "filing_id": filing_id,
                "message": error_message,
                "retries": self.request.retries
            }
    
    finally:
        # Always clean up the database session
        if db:
            self.close_db(db)


def validate_completed_filing(filing: Filing) -> Dict:
    """
    Validate a completed filing for quality and completeness
    """
    issues = []
    
    # Check unified analysis
    if not filing.unified_analysis:
        issues.append("Missing unified analysis")
    elif len(filing.unified_analysis) < 500:
        issues.append("Unified analysis too short")
    
    # Check feed summary
    if not filing.unified_feed_summary:
        issues.append("Missing feed summary")
    elif len(filing.unified_feed_summary) > 300:
        issues.append("Feed summary too long")
    
    # Check filing-specific requirements
    if filing.filing_type.value == "10-Q":
        if not filing.financial_highlights and not filing.core_metrics:
            issues.append("Missing financial highlights for 10-Q")
    
    elif filing.filing_type.value == "8-K":
        if not filing.event_type:
            issues.append("Missing event type for 8-K")
    
    elif filing.filing_type.value == "S-1":
        if not filing.financial_summary and not filing.financial_highlights:
            issues.append("Missing financial summary for S-1")
    
    # Check data source markings for v5
    if filing.analysis_version == "v5":
        if filing.unified_analysis and '[DOC:' not in filing.unified_analysis:
            issues.append("Missing data source markings in v5 analysis")
    
    return {
        'is_valid': len(issues) == 0,
        'issues': issues
    }


@celery_app.task(base=FilingTask)
def process_pending_filings():
    """
    Find and process all pending filings
    This task can be scheduled to run periodically
    ENHANCED: Added batch size control and validation
    FIXED: Use timezone-aware datetime for comparisons
    """
    try:
        # 使用上下文管理器确保会话清理
        with get_task_db() as db:
            # Get all pending filings with limit for batch processing
            pending_filings = db.query(Filing).filter(
                Filing.status == ProcessingStatus.PENDING
            ).order_by(
                Filing.filing_date.desc()  # Process newest first
            ).limit(50).all()
            
            logger.info(f"Found {len(pending_filings)} pending filings")
            
            # Validate and queue each filing
            filing_ids = []
            skipped = 0
            
            # FIXED: Use timezone-aware datetime
            current_time_utc = datetime.now(timezone.utc)
            
            for filing in pending_filings:
                # Quick validation before queueing
                if not filing.accession_number or not filing.company_id:
                    logger.warning(f"Skipping invalid pending filing {filing.id}")
                    skipped += 1
                    continue
                
                # Check if not already being processed
                if filing.processing_started_at:
                    if filing.processing_started_at.tzinfo is None:
                        processing_started_utc = filing.processing_started_at.replace(tzinfo=timezone.utc)
                    else:
                        processing_started_utc = filing.processing_started_at.astimezone(timezone.utc)
                    
                    time_since_start = current_time_utc - processing_started_utc
                    if time_since_start.total_seconds() < 300:  # Less than 5 minutes
                        logger.info(f"Filing {filing.id} already being processed")
                        skipped += 1
                        continue
                
                # Queue the filing with delay to avoid overwhelming the system
                delay = len(filing_ids) * 2  # 2 seconds between each
                process_filing_task.apply_async(args=[filing.id], countdown=delay)
                filing_ids.append(filing.id)
            
            return {
                "status": "success",
                "queued": len(filing_ids),
                "skipped": skipped,
                "filing_ids": filing_ids
            }
        
    except Exception as e:
        logger.error(f"Error queuing pending filings: {e}", exc_info=True)
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
    return {"status": "notifications_sent"}


# Add missing imports
from pathlib import Path
import re
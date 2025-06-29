#!/usr/bin/env python3
"""
Test Celery async task processing
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from app.tasks.filing_tasks import process_filing_task
from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus


def test_async_processing():
    """Test async processing of a filing"""
    
    print("Celery Async Processing Test")
    print("=" * 50)
    
    # Get a filing to process
    db = SessionLocal()
    
    # Reset a filing to PENDING for testing
    filing = db.query(Filing).first()
    if filing:
        filing.status = ProcessingStatus.PENDING
        filing.ai_summary = None
        filing.key_questions = None
        db.commit()
        
        print(f"Filing to process:")
        print(f"  Company: {filing.company.ticker}")
        print(f"  Type: {filing.filing_type.value}")
        print(f"  Status: {filing.status.value}")
        
        print(f"\nQueuing filing {filing.id} for async processing...")
        
        # Queue the task
        result = process_filing_task.delay(filing.id)
        
        print(f"Task ID: {result.id}")
        print(f"Task queued successfully!")
        
        print("\nTo check task status:")
        print(f"  from app.core.celery_app import celery_app")
        print(f"  result = celery_app.AsyncResult('{result.id}')")
        print(f"  print(result.status)")
        
    else:
        print("No filings found in database")
    
    db.close()


if __name__ == "__main__":
    test_async_processing()
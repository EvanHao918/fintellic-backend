#!/usr/bin/env python3
"""
Test full async processing flow
"""
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from app.tasks.filing_tasks import process_filing_task
from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
from app.core.celery_app import celery_app


def test_full_flow():
    """Test complete async processing flow"""
    
    print("Full Async Processing Flow Test")
    print("=" * 50)
    
    db = SessionLocal()
    
    # Reset filing to PENDING
    filing = db.query(Filing).first()
    if filing:
        print(f"\nResetting filing to PENDING state...")
        filing.status = ProcessingStatus.PENDING
        filing.ai_summary = None
        filing.key_questions = None
        filing.management_tone = None
        filing.processing_started_at = None
        filing.processing_completed_at = None
        db.commit()
        
        print(f"Filing reset:")
        print(f"  Company: {filing.company.ticker}")
        print(f"  Type: {filing.filing_type.value}")
        print(f"  Status: {filing.status.value}")
        
        # Queue the task
        print(f"\nQueuing filing for async processing...")
        result = process_filing_task.delay(filing.id)
        print(f"Task ID: {result.id}")
        
        # Monitor progress
        print("\nMonitoring task progress...")
        for i in range(60):  # Max 60 seconds
            task_result = celery_app.AsyncResult(result.id)
            
            if task_result.ready():
                print(f"\n✓ Task completed!")
                print(f"Result: {task_result.result}")
                
                # Check database
                db.refresh(filing)
                print(f"\nFiling final status: {filing.status.value}")
                
                if filing.ai_summary:
                    print(f"\nAI Summary generated ({len(filing.ai_summary)} chars):")
                    print("-" * 50)
                    print(filing.ai_summary[:500] + "...")
                    
                if filing.management_tone:
                    print(f"\nManagement Tone: {filing.management_tone.value}")
                    
                if filing.key_questions:
                    print(f"\nGenerated {len(filing.key_questions)} Q&A pairs")
                
                break
            else:
                print(f".", end="", flush=True)
                time.sleep(1)
        else:
            print("\nTask timed out!")
    
    db.close()


if __name__ == "__main__":
    test_full_flow()
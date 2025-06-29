#!/usr/bin/env python3
"""
Test full async processing flow with improved monitoring
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
    
    # Get first filing
    filing = db.query(Filing).first()
    if not filing:
        print("No filings found in database")
        return
    
    # Check current status
    print(f"\nCurrent filing status: {filing.status.value}")
    
    if filing.status == ProcessingStatus.COMPLETED:
        print("Filing already completed. Resetting to PENDING...")
        # Reset filing to PENDING
        filing.status = ProcessingStatus.PENDING
        filing.ai_summary = None
        filing.key_questions = None
        filing.management_tone = None
        filing.processing_started_at = None
        filing.processing_completed_at = None
        filing.error_message = None
        db.commit()
        
        print(f"Filing reset:")
        print(f"  Company: {filing.company.ticker}")
        print(f"  Type: {filing.filing_type.value}")
        print(f"  Status: {filing.status.value}")
    
    # Queue the task
    print(f"\nQueuing filing for async processing...")
    result = process_filing_task.delay(filing.id)
    print(f"Task ID: {result.id}")
    
    # Monitor progress with better feedback
    print("\nMonitoring task progress (timeout: 120 seconds)...")
    print("Status: ", end="", flush=True)
    
    start_time = time.time()
    last_status = None
    
    for i in range(120):  # 120 seconds timeout
        task_result = celery_app.AsyncResult(result.id)
        
        # Show status changes
        if task_result.status != last_status:
            print(f"\n{task_result.status}", end="", flush=True)
            last_status = task_result.status
        else:
            print(".", end="", flush=True)
        
        if task_result.ready():
            elapsed = time.time() - start_time
            print(f"\n\n✓ Task completed in {elapsed:.1f} seconds!")
            
            if task_result.successful():
                print(f"Result: {task_result.result}")
                
                # Check database
                db.refresh(filing)
                print(f"\nFiling final status: {filing.status.value}")
                
                if filing.ai_summary:
                    print(f"\n📝 AI Summary generated ({len(filing.ai_summary)} chars):")
                    print("-" * 50)
                    print(filing.ai_summary[:500] + "...")
                    
                if filing.management_tone:
                    print(f"\n🎭 Management Tone: {filing.management_tone.value}")
                    print(f"Explanation: {filing.tone_explanation[:200]}...")
                    
                if filing.key_questions:
                    print(f"\n❓ Generated {len(filing.key_questions)} Q&A pairs")
                    if filing.key_questions:
                        print(f"Q1: {filing.key_questions[0]['question']}")
                        print(f"A1: {filing.key_questions[0]['answer'][:100]}...")
                
                if filing.key_tags:
                    print(f"\n🏷️ Tags: {', '.join(filing.key_tags)}")
            else:
                print(f"\n❌ Task failed!")
                print(f"Error: {task_result.info}")
                
            break
        
        time.sleep(1)
    else:
        print(f"\n\nTask timed out after {time.time() - start_time:.1f} seconds!")
        print(f"Final status: {task_result.status}")
        print("\nPossible reasons:")
        print("1. Celery worker not running")
        print("2. Task still processing (check Celery logs)")
        print("3. Task stuck or failed silently")
        
        # Check if filing status changed
        db.refresh(filing)
        print(f"\nDatabase filing status: {filing.status.value}")
    
    db.close()


if __name__ == "__main__":
    test_full_flow()
#!/usr/bin/env python3
"""
Check filing processing results
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).parent))

from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
from app.core.celery_app import celery_app


def check_results():
    """Check filing processing results"""
    print("Filing Processing Results")
    print("=" * 80)
    
    db = SessionLocal()
    
    # Get status counts
    print("\nProcessing Status Summary:")
    for status in ProcessingStatus:
        count = db.query(Filing).filter(Filing.status == status).count()
        print(f"  {status.value:20}: {count}")
    
    # Get completed filings
    completed = db.query(Filing).filter(
        Filing.status == ProcessingStatus.COMPLETED
    ).all()
    
    if completed:
        print(f"\n✅ Completed Filings ({len(completed)}):")
        print("-" * 80)
        
        for filing in completed:
            print(f"\n{filing.company.ticker} - {filing.filing_type.value}")
            print(f"Filed: {filing.filing_date}")
            print(f"Processed: {filing.processing_completed_at}")
            
            if filing.ai_summary:
                print(f"\n📝 AI Summary ({len(filing.ai_summary)} chars):")
                print("-" * 40)
                print(filing.ai_summary[:500] + "...")
            
            if filing.management_tone:
                print(f"\n🎭 Management Tone: {filing.management_tone.value}")
                print(f"Explanation: {filing.tone_explanation}")
            
            if filing.key_questions:
                print(f"\n❓ Key Questions ({len(filing.key_questions)}):")
                for i, qa in enumerate(filing.key_questions[:3], 1):
                    print(f"\nQ{i}: {qa['question']}")
                    print(f"A{i}: {qa['answer']}")
            
            if filing.key_tags:
                print(f"\n🏷️ Tags: {', '.join(filing.key_tags)}")
            
            print("\n" + "=" * 80)
    
    # Get failed filings
    failed = db.query(Filing).filter(
        Filing.status == ProcessingStatus.FAILED
    ).all()
    
    if failed:
        print(f"\n❌ Failed Filings ({len(failed)}):")
        for filing in failed:
            print(f"  {filing.company.ticker} - {filing.filing_type.value}: {filing.error_message}")
    
    # Check specific task status
    task_id = input("\nEnter task ID to check (or press Enter to skip): ").strip()
    if task_id:
        result = celery_app.AsyncResult(task_id)
        print(f"\nTask {task_id}:")
        print(f"  Status: {result.status}")
        if result.ready():
            print(f"  Result: {result.result}")
    
    db.close()


if __name__ == "__main__":
    check_results()
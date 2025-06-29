#!/usr/bin/env python3
"""
Test script for Day 4.5 enhancements
Tests differentiated processing for 10-K, 10-Q, 8-K, and S-1 filings
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from app.core.database import SessionLocal
from app.models.filing import Filing, FilingType, ProcessingStatus
from app.services.ai_processor import ai_processor
from app.services.filing_downloader import filing_downloader
from app.tasks.filing_tasks import process_filing_task


async def test_filing_types():
    """Test different filing types"""
    print("=" * 80)
    print("Day 4.5 Enhancement Test")
    print("Testing differentiated processing for 10-K, 10-Q, 8-K, and S-1")
    print("=" * 80)
    
    db = SessionLocal()
    
    try:
        # Get filings of each type
        filing_types = [
            FilingType.FORM_10K,
            FilingType.FORM_10Q,
            FilingType.FORM_8K,
            FilingType.FORM_S1
        ]
        
        for filing_type in filing_types:
            print(f"\n{'='*60}")
            print(f"Testing {filing_type.value} Processing")
            print('='*60)
            
            # Find a filing of this type
            filing = db.query(Filing).filter(
                Filing.filing_type == filing_type
            ).first()
            
            if not filing:
                print(f"❌ No {filing_type.value} filing found in database")
                continue
            
            print(f"✅ Found {filing_type.value} filing:")
            print(f"   Company: {filing.company.ticker} - {filing.company.name}")
            print(f"   Date: {filing.filing_date}")
            print(f"   Status: {filing.status.value}")
            
            # Reset filing to PENDING for testing
            if filing.status == ProcessingStatus.COMPLETED:
                print("   Resetting to PENDING for testing...")
                filing.status = ProcessingStatus.PENDING
                filing.ai_summary = None
                filing.key_questions = None
                filing.key_tags = None
                filing.management_tone = None
                filing.financial_highlights = None
                db.commit()
            
            # Test processing
            print(f"\n   Processing {filing_type.value}...")
            
            # Check if filing is downloaded
            filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
            if not filing_dir.exists():
                print("   Downloading filing first...")
                success = await filing_downloader.download_filing(db, filing)
                if not success:
                    print(f"   ❌ Failed to download filing")
                    continue
            
            # Process with AI
            print("   Running AI processing...")
            start_time = datetime.now()
            
            success = await ai_processor.process_filing(db, filing)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            if success:
                # Reload filing to get results
                db.refresh(filing)
                
                print(f"\n   ✅ Processing successful in {processing_time:.1f} seconds!")
                
                # Show results based on filing type
                if filing_type == FilingType.FORM_10K:
                    print("\n   📊 10-K Annual Report Results:")
                    print(f"   Summary length: {len(filing.ai_summary)} chars")
                    print(f"   Tags: {', '.join(filing.key_tags or [])}")
                    if filing.financial_highlights:
                        print(f"   Financial data extracted: {len(filing.financial_highlights)} items")
                    
                elif filing_type == FilingType.FORM_10Q:
                    print("\n   📊 10-Q Quarterly Report Results:")
                    print(f"   Summary length: {len(filing.ai_summary)} chars")
                    print(f"   Tags: {', '.join(filing.key_tags or [])}")
                    if filing.financial_highlights:
                        print(f"   Financial data extracted: {len(filing.financial_highlights)} items")
                
                elif filing_type == FilingType.FORM_8K:
                    print("\n   📊 8-K Current Report Results:")
                    print(f"   Summary length: {len(filing.ai_summary)} chars")
                    print(f"   Tags: {', '.join(filing.key_tags or [])}")
                    # Check for event type in summary
                    if "executive" in filing.ai_summary.lower():
                        print("   Event type: Executive Change")
                    elif "earnings" in filing.ai_summary.lower():
                        print("   Event type: Earnings")
                    
                elif filing_type == FilingType.FORM_S1:
                    print("\n   📊 S-1 IPO Filing Results:")
                    print(f"   Summary length: {len(filing.ai_summary)} chars")
                    print(f"   Tags: {', '.join(filing.key_tags or [])}")
                    print(f"   IPO-specific content detected: {'IPO' in str(filing.key_tags)}")
                
                # Common results
                print(f"\n   Management Tone: {filing.management_tone.value if filing.management_tone else 'None'}")
                print(f"   Tone Explanation: {filing.tone_explanation[:100] if filing.tone_explanation else 'None'}...")
                print(f"   Questions Generated: {len(filing.key_questions) if filing.key_questions else 0}")
                
                if filing.key_questions and len(filing.key_questions) > 0:
                    print(f"\n   Sample Question: {filing.key_questions[0]['question']}")
                    print(f"   Sample Answer: {filing.key_questions[0]['answer'][:100]}...")
                
            else:
                print(f"\n   ❌ Processing failed!")
                print(f"   Error: {filing.error_message}")
    
    finally:
        db.close()
    
    print("\n" + "="*80)
    print("Test Complete!")
    print("="*80)


async def test_async_processing():
    """Test async processing through Celery"""
    print("\n" + "="*80)
    print("Testing Async Processing")
    print("="*80)
    
    db = SessionLocal()
    
    try:
        # Find a PENDING filing
        filing = db.query(Filing).filter(
            Filing.status == ProcessingStatus.PENDING
        ).first()
        
        if not filing:
            # Reset one for testing
            filing = db.query(Filing).first()
            if filing:
                filing.status = ProcessingStatus.PENDING
                db.commit()
        
        if filing:
            print(f"\nQueuing filing for async processing:")
            print(f"Company: {filing.company.ticker}")
            print(f"Type: {filing.filing_type.value}")
            
            # Queue the task
            result = process_filing_task.delay(filing.id)
            print(f"\nTask ID: {result.id}")
            print("Task queued! Check Celery worker output.")
        else:
            print("No filings found for testing")
    
    finally:
        db.close()


async def main():
    """Main test function"""
    print("\nDay 4.5 Test Suite")
    print("==================\n")
    
    # Test 1: Direct processing of different filing types
    await test_filing_types()
    
    # Test 2: Async processing
    # await test_async_processing()
    
    print("\n✅ All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
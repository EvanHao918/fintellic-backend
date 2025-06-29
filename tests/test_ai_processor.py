#!/usr/bin/env python3
"""
Test AI processing of filings
"""
import asyncio
import sys
from pathlib import Path
import os
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

# Load environment variables
load_dotenv()

from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
from app.services.ai_processor import ai_processor
from app.core.config import settings


async def test_ai_processing():
    """Test AI processing on a filing"""
    
    # Check if OpenAI API key is available through settings
    try:
        from app.core.config import settings
        api_key = settings.OPENAI_API_KEY
    except:
        api_key = None
    
    if not api_key:
        print("❌ OPENAI_API_KEY not found")
        print("Please make sure your .env file contains: OPENAI_API_KEY=your-key-here")
        return
    
    print(f"✅ OpenAI API key loaded: {api_key[:20]}...")
    
    db = SessionLocal()
    
    try:
        # Get a filing that's ready for AI processing
        filing = db.query(Filing).filter(
            Filing.status.in_([ProcessingStatus.PARSING, ProcessingStatus.DOWNLOADING])
        ).first()
        
        if not filing:
            print("❌ No filings ready for AI processing")
            print("Status check:")
            
            # Show all filings and their status
            all_filings = db.query(Filing).all()
            for f in all_filings:
                print(f"  {f.company.ticker} - {f.filing_type.value}: {f.status.value}")
            
            return
        
        print(f"\nProcessing filing:")
        print(f"Company: {filing.company.ticker} - {filing.company.name}")
        print(f"Type: {filing.filing_type.value}")
        print(f"Date: {filing.filing_date}")
        print(f"Current Status: {filing.status.value}")
        
        print("\n" + "="*50)
        print("Starting AI processing...")
        print("="*50)
        
        # Process the filing
        success = await ai_processor.process_filing(db, filing)
        
        if success:
            print("\n✅ AI processing successful!")
            
            # Reload filing to get updated data
            db.refresh(filing)
            
            print("\n📝 AI Summary:")
            print("-" * 50)
            print(filing.ai_summary)
            
            print(f"\n🎭 Management Tone: {filing.management_tone.value}")
            print(f"Explanation: {filing.tone_explanation}")
            
            if filing.key_questions:
                print("\n❓ Key Questions:")
                print("-" * 50)
                for i, qa in enumerate(filing.key_questions, 1):
                    print(f"\nQ{i}: {qa['question']}")
                    print(f"A{i}: {qa['answer']}")
            
            if filing.key_tags:
                print(f"\n🏷️ Tags: {', '.join(filing.key_tags)}")
                
        else:
            print("\n❌ AI processing failed!")
            print(f"Error: {filing.error_message}")
            
    finally:
        db.close()


async def main():
    print("AI Processor Test")
    print("=" * 50)
    
    await test_ai_processing()


if __name__ == "__main__":
    asyncio.run(main())
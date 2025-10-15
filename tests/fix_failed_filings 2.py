#!/usr/bin/env python
"""
Fix filings that failed due to OpenAI API key issue
"""
import asyncio
import sys
sys.path.append('.')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.filing import Filing, ProcessingStatus
from app.services.ai_processor import ai_processor
from app.core.config import settings

# Create database connection
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async def fix_failed_filings():
    db = SessionLocal()
    
    try:
        # Find all filings with API error
        failed_filings = db.query(Filing).filter(
            Filing.ai_summary.like('%Analysis generation failed%')
        ).all()
        
        print(f"Found {len(failed_filings)} failed filings to reprocess")
        
        for i, filing in enumerate(failed_filings):
            print(f"\n[{i+1}/{len(failed_filings)}] Processing {filing.company.ticker} - {filing.filing_type.value}")
            
            # Reset status to trigger reprocessing
            filing.status = ProcessingStatus.DOWNLOADED
            filing.ai_summary = None
            filing.error_message = None
            db.commit()
            
            # Reprocess with AI
            try:
                success = await ai_processor.process_filing(db, filing)
                if success:
                    print(f"✅ Successfully processed {filing.company.ticker}")
                else:
                    print(f"❌ Failed to process {filing.company.ticker}")
            except Exception as e:
                print(f"❌ Error processing {filing.company.ticker}: {str(e)}")
            
            # Add small delay to avoid rate limits
            await asyncio.sleep(1)
        
        print("\n✅ Reprocessing complete!")
        
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(fix_failed_filings())

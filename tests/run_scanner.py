#!/usr/bin/env python3
"""
Run the EDGAR scanner to fetch new filings
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from app.services.edgar_scanner import edgar_scanner
from app.services.scheduler import filing_scheduler


async def main():
    print("SEC EDGAR Scanner")
    print("=" * 50)
    
    # Check S&P 500 companies loaded
    stats = await edgar_scanner.get_sp500_stats()
    print(f"\nMonitoring {stats['total_sp500_companies']} S&P 500 companies")
    print(f"Sample companies: {', '.join(stats['sample_companies'][:3])}")
    
    # Run a single scan
    print("\nRunning scan for new filings...")
    new_filings = await edgar_scanner.scan_for_new_filings()
    
    if new_filings:
        print(f"\n✅ Found {len(new_filings)} new filings:")
        for filing in new_filings[:5]:  # Show first 5
            print(f"  - {filing['ticker']} {filing['form_type']} ({filing['filing_date']})")
    else:
        print("\n❌ No new filings found")
        print("This is normal - most times there won't be new filings")
        print("Filings are usually released around 4-6 PM EST")
    
    # Show current database status
    from app.core.database import SessionLocal
    from app.models.filing import Filing, ProcessingStatus
    
    db = SessionLocal()
    try:
        total = db.query(Filing).count()
        pending = db.query(Filing).filter(Filing.status == ProcessingStatus.PENDING).count()
        failed = db.query(Filing).filter(Filing.status == ProcessingStatus.FAILED).count()
        
        print(f"\nDatabase status:")
        print(f"  Total filings: {total}")
        print(f"  Pending download: {pending}")
        print(f"  Failed: {failed}")
        
        # If we have failed filings, reset them to pending
        if failed > 0:
            print(f"\nResetting {failed} failed filings to PENDING status...")
            db.query(Filing).filter(
                Filing.status == ProcessingStatus.FAILED
            ).update({
                Filing.status: ProcessingStatus.PENDING,
                Filing.error_message: None
            })
            db.commit()
            print("✅ Reset complete")
            
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
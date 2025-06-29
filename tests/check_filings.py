#!/usr/bin/env python3
"""
Check the status of all filings in the database
"""
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
from app.models.company import Company


def main():
    print("Filing Status Check")
    print("=" * 80)
    
    db = SessionLocal()
    
    try:
        # Get all filings with company info
        filings = db.query(Filing).join(Company).all()
        
        if not filings:
            print("No filings found in database")
            return
        
        print(f"Total filings: {len(filings)}\n")
        
        # Group by status
        status_counts = {}
        for filing in filings:
            status = filing.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print("Status summary:")
        for status, count in status_counts.items():
            print(f"  {status}: {count}")
        
        print(f"\nDetailed filing list:")
        print("-" * 80)
        print(f"{'Company':<10} {'Type':<8} {'Date':<12} {'Status':<15} {'Accession':<25}")
        print("-" * 80)
        
        for filing in filings:
            print(f"{filing.company.ticker:<10} "
                  f"{filing.filing_type.value:<8} "
                  f"{filing.filing_date.strftime('%Y-%m-%d'):<12} "
                  f"{filing.status.value:<15} "
                  f"{filing.accession_number:<25}")
            
            # Check if files exist
            filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
            if filing_dir.exists():
                files = list(filing_dir.glob("*"))
                if files:
                    print(f"    Files: {', '.join(f.name for f in files)}")
        
        # Reset parsing filings to pending for testing
        parsing_count = db.query(Filing).filter(Filing.status == ProcessingStatus.PARSING).count()
        if parsing_count > 0:
            print(f"\n{'='*80}")
            response = input(f"\nReset {parsing_count} PARSING filing(s) to PENDING? (y/n): ")
            if response.lower() == 'y':
                db.query(Filing).filter(
                    Filing.status == ProcessingStatus.PARSING
                ).update({
                    Filing.status: ProcessingStatus.PENDING
                })
                db.commit()
                print("✅ Reset complete")
                
    finally:
        db.close()


if __name__ == "__main__":
    main()
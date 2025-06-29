#!/usr/bin/env python3
"""
Test downloading a specific filing
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
from app.services.filing_downloader import filing_downloader


async def test_download():
    """Test downloading a recent filing"""
    db = SessionLocal()
    
    try:
        # Get a PENDING filing to test
        filing = db.query(Filing).filter(
            Filing.status == ProcessingStatus.PENDING
        ).first()
        
        if not filing:
            print("❌ No pending filings found in database")
            print("Please run the scanner first to populate filings")
            return
        
        print(f"\nFound filing to test:")
        print(f"Company: {filing.company.ticker} - {filing.company.name}")
        print(f"Type: {filing.filing_type.value}")
        print(f"Date: {filing.filing_date}")
        print(f"Accession: {filing.accession_number}")
        
        print("\nAttempting download...")
        
        # Test the download
        success = await filing_downloader.download_filing(db, filing)
        
        if success:
            print("✅ Download successful!")
            
            # Check if file exists
            filing_dir = filing_downloader._get_filing_directory(filing)
            files = list(filing_dir.glob("*.htm"))
            
            if files:
                print(f"\nDownloaded files:")
                for file in files:
                    size_kb = file.stat().st_size / 1024
                    print(f"  - {file.name} ({size_kb:.1f} KB)")
            else:
                print("⚠️  No files found in directory")
        else:
            print("❌ Download failed!")
            print(f"Error: {filing.error_message}")
            
    finally:
        db.close()


async def main():
    print("SEC Filing Download Test")
    print("=" * 50)
    
    # Test connection first
    print("\n1. Testing connection...")
    connected = await filing_downloader.test_connection()
    
    if not connected:
        print("❌ Cannot connect to SEC. Please check your internet connection.")
        return
    
    # Test download
    print("\n2. Testing filing download...")
    await test_download()


if __name__ == "__main__":
    asyncio.run(main())
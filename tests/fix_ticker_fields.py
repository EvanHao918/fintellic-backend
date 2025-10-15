#!/usr/bin/env python3
"""
Script to fix missing ticker fields in filings table
Run this to ensure all filings have ticker populated from their company
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import logging
from app.core.database import SessionLocal
from app.models.filing import Filing
from app.models.company import Company

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_ticker_fields():
    """
    Update all filings with missing ticker fields
    """
    db = SessionLocal()
    try:
        logger.info("Starting ticker field fix...")
        
        # Method 1: Direct SQL update (fastest)
        logger.info("Running SQL update for missing tickers...")
        
        sql = text("""
            UPDATE filings 
            SET ticker = companies.ticker 
            FROM companies 
            WHERE filings.company_id = companies.id 
            AND (filings.ticker IS NULL OR filings.ticker = '')
            AND companies.ticker IS NOT NULL
            AND companies.ticker != ''
        """)
        
        result = db.execute(sql)
        db.commit()
        
        updated_count = result.rowcount
        logger.info(f"Updated {updated_count} filings via SQL")
        
        # Method 2: Check for any remaining issues using ORM
        logger.info("Checking for remaining filings without ticker...")
        
        filings_without_ticker = db.query(Filing).filter(
            (Filing.ticker == None) | (Filing.ticker == '')
        ).all()
        
        if filings_without_ticker:
            logger.info(f"Found {len(filings_without_ticker)} filings still without ticker")
            
            fixed_count = 0
            no_company_ticker = 0
            
            for filing in filings_without_ticker:
                if filing.company and filing.company.ticker:
                    filing.ticker = filing.company.ticker
                    fixed_count += 1
                else:
                    no_company_ticker += 1
                    if filing.company:
                        logger.warning(f"Filing {filing.id} - Company {filing.company.name} has no ticker")
                    else:
                        logger.warning(f"Filing {filing.id} has no company relationship")
            
            if fixed_count > 0:
                db.commit()
                logger.info(f"Fixed {fixed_count} additional filings via ORM")
            
            if no_company_ticker > 0:
                logger.warning(f"{no_company_ticker} filings have companies without tickers (likely S-1 filings)")
        else:
            logger.info("✅ All filings have tickers!")
        
        # Verify the fix
        logger.info("Verifying the fix...")
        
        # Count filings with tickers
        total_filings = db.query(Filing).count()
        filings_with_ticker = db.query(Filing).filter(
            Filing.ticker != None,
            Filing.ticker != ''
        ).count()
        
        logger.info(f"Total filings: {total_filings}")
        logger.info(f"Filings with ticker: {filings_with_ticker}")
        logger.info(f"Filings without ticker: {total_filings - filings_with_ticker}")
        
        # Show sample of fixed filings
        sample_filings = db.query(Filing).filter(
            Filing.ticker != None
        ).limit(5).all()
        
        logger.info("\nSample fixed filings:")
        for filing in sample_filings:
            logger.info(f"  - Filing {filing.id}: {filing.ticker} - {filing.filing_type.value} ({filing.filing_date})")
        
        logger.info("\n✅ Ticker field fix completed!")
        
    except Exception as e:
        logger.error(f"Error fixing ticker fields: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def verify_ticker_consistency():
    """
    Verify that filing tickers match company tickers
    """
    db = SessionLocal()
    try:
        logger.info("\nVerifying ticker consistency...")
        
        # Find mismatches
        sql = text("""
            SELECT f.id, f.ticker as filing_ticker, c.ticker as company_ticker, c.name
            FROM filings f
            JOIN companies c ON f.company_id = c.id
            WHERE f.ticker != c.ticker
            AND f.ticker IS NOT NULL
            AND c.ticker IS NOT NULL
            LIMIT 10
        """)
        
        mismatches = db.execute(sql).fetchall()
        
        if mismatches:
            logger.warning(f"Found {len(mismatches)} ticker mismatches:")
            for row in mismatches:
                logger.warning(f"  - Filing {row[0]}: '{row[1]}' vs Company '{row[2]}' ({row[3]})")
            
            # Optionally fix mismatches
            response = input("\nFix mismatches? (y/n): ")
            if response.lower() == 'y':
                sql_fix = text("""
                    UPDATE filings 
                    SET ticker = companies.ticker 
                    FROM companies 
                    WHERE filings.company_id = companies.id 
                    AND filings.ticker != companies.ticker
                """)
                
                result = db.execute(sql_fix)
                db.commit()
                logger.info(f"Fixed {result.rowcount} mismatches")
        else:
            logger.info("✅ No ticker mismatches found!")
        
    except Exception as e:
        logger.error(f"Error verifying ticker consistency: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("TICKER FIELD FIX UTILITY")
    print("=" * 60)
    
    fix_ticker_fields()
    verify_ticker_consistency()
    
    print("\n" + "=" * 60)
    print("COMPLETED")
    print("=" * 60)
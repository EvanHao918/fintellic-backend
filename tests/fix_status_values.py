#!/usr/bin/env python3
"""
Script to fix status value case inconsistency in filings table
Converts all uppercase status values to lowercase to match enum definition
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, func
from sqlalchemy.orm import Session
import logging
from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_status_values():
    """
    Check current status values in database
    """
    db = SessionLocal()
    try:
        logger.info("Checking current status values in database...")
        
        # Get unique status values
        sql = text("""
            SELECT DISTINCT status, COUNT(*) as count
            FROM filings
            GROUP BY status
            ORDER BY status
        """)
        
        results = db.execute(sql).fetchall()
        
        logger.info("\nCurrent status values in database:")
        logger.info("-" * 40)
        
        uppercase_count = 0
        lowercase_count = 0
        
        for row in results:
            status = row[0]
            count = row[1]
            
            if status and status.isupper():
                logger.warning(f"  UPPERCASE: '{status}' - {count} records")
                uppercase_count += count
            elif status and status.islower():
                logger.info(f"  lowercase: '{status}' - {count} records")
                lowercase_count += count
            else:
                logger.info(f"  {status}: {count} records")
        
        logger.info("-" * 40)
        logger.info(f"Total uppercase: {uppercase_count}")
        logger.info(f"Total lowercase: {lowercase_count}")
        
        return uppercase_count > 0
        
    except Exception as e:
        logger.error(f"Error checking status values: {e}")
        return False
    finally:
        db.close()


def fix_status_values():
    """
    Convert all uppercase status values to lowercase
    """
    db = SessionLocal()
    try:
        logger.info("\nFixing status values...")
        
        # Map uppercase to lowercase values
        status_mapping = {
            'PENDING': 'pending',
            'DOWNLOADING': 'downloading',
            'PARSING': 'parsing',
            'ANALYZING': 'analyzing',
            'COMPLETED': 'completed',
            'FAILED': 'failed',
            'SKIPPED': 'skipped'
        }
        
        total_updated = 0
        
        for old_status, new_status in status_mapping.items():
            sql = text("""
                UPDATE filings 
                SET status = :new_status 
                WHERE status = :old_status
            """)
            
            result = db.execute(sql, {'old_status': old_status, 'new_status': new_status})
            count = result.rowcount
            
            if count > 0:
                logger.info(f"  Updated {count} records from '{old_status}' to '{new_status}'")
                total_updated += count
        
        db.commit()
        
        if total_updated > 0:
            logger.info(f"\n✅ Successfully updated {total_updated} records to lowercase status values")
        else:
            logger.info("\n✅ No uppercase status values found - database is already consistent!")
        
        return total_updated
        
    except Exception as e:
        logger.error(f"Error fixing status values: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def verify_enum_values():
    """
    Verify that all status values match the ProcessingStatus enum
    """
    db = SessionLocal()
    try:
        logger.info("\nVerifying status values against ProcessingStatus enum...")
        
        # Get valid enum values
        valid_statuses = [status.value for status in ProcessingStatus]
        logger.info(f"Valid ProcessingStatus enum values: {valid_statuses}")
        
        # Check for any invalid values
        sql = text("""
            SELECT DISTINCT status, COUNT(*) as count
            FROM filings
            WHERE status NOT IN :valid_statuses
            GROUP BY status
        """)
        
        invalid = db.execute(sql, {'valid_statuses': tuple(valid_statuses)}).fetchall()
        
        if invalid:
            logger.error("Found invalid status values:")
            for row in invalid:
                logger.error(f"  - '{row[0]}': {row[1]} records")
            return False
        else:
            logger.info("✅ All status values are valid!")
            return True
            
    except Exception as e:
        logger.error(f"Error verifying enum values: {e}")
        return False
    finally:
        db.close()


def update_database_enum():
    """
    Update the PostgreSQL enum type to ensure it has all values
    """
    db = SessionLocal()
    try:
        logger.info("\nChecking PostgreSQL enum type...")
        
        # Get current enum values from database
        sql = text("""
            SELECT enumlabel 
            FROM pg_enum 
            WHERE enumtypid = (
                SELECT oid FROM pg_type WHERE typname = 'processingstatus'
            )
            ORDER BY enumsortorder
        """)
        
        results = db.execute(sql).fetchall()
        
        if results:
            current_values = [row[0] for row in results]
            logger.info(f"Current PostgreSQL enum values: {current_values}")
            
            # Check if we need to add any values
            required_values = ['pending', 'downloading', 'parsing', 'analyzing', 'completed', 'failed', 'skipped']
            missing_values = [v for v in required_values if v not in current_values]
            
            if missing_values:
                logger.info(f"Missing enum values: {missing_values}")
                
                for value in missing_values:
                    try:
                        sql_add = text(f"ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS '{value}'")
                        db.execute(sql_add)
                        logger.info(f"  Added '{value}' to enum")
                    except Exception as e:
                        logger.warning(f"  Could not add '{value}': {e}")
                
                db.commit()
            else:
                logger.info("✅ PostgreSQL enum has all required values")
        else:
            logger.warning("Could not fetch enum values from PostgreSQL")
            
    except Exception as e:
        logger.error(f"Error updating database enum: {e}")
    finally:
        db.close()


def show_status_distribution():
    """
    Show distribution of filing statuses after fix
    """
    db = SessionLocal()
    try:
        logger.info("\nFinal status distribution:")
        logger.info("-" * 40)
        
        sql = text("""
            SELECT status, COUNT(*) as count,
                   ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
            FROM filings
            GROUP BY status
            ORDER BY count DESC
        """)
        
        results = db.execute(sql).fetchall()
        
        for row in results:
            status = row[0] or 'NULL'
            count = row[1]
            percentage = row[2]
            logger.info(f"  {status:15} : {count:6} records ({percentage:5}%)")
        
        total = db.query(Filing).count()
        logger.info("-" * 40)
        logger.info(f"  {'TOTAL':15} : {total:6} records")
        
    except Exception as e:
        logger.error(f"Error showing status distribution: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("STATUS VALUE CASE FIX UTILITY")
    print("=" * 60)
    
    # Step 1: Check current status
    has_uppercase = check_status_values()
    
    if has_uppercase:
        # Step 2: Fix uppercase values
        response = input("\nConvert uppercase status values to lowercase? (y/n): ")
        if response.lower() == 'y':
            fixed_count = fix_status_values()
            
            # Step 3: Verify the fix
            check_status_values()
    
    # Step 4: Verify enum values
    verify_enum_values()
    
    # Step 5: Update database enum if needed
    update_database_enum()
    
    # Step 6: Show final distribution
    show_status_distribution()
    
    print("\n" + "=" * 60)
    print("COMPLETED")
    print("=" * 60)
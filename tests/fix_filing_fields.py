#!/usr/bin/env python3
"""
Fix filing fields that have empty dicts stored as JSON
This script safely checks which columns exist before trying to fix them
"""
import sys
import os
import json
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

def get_existing_columns(engine):
    """Get list of existing columns in the filings table"""
    inspector = inspect(engine)
    columns = inspector.get_columns('filings')
    return [col['name'] for col in columns]

def check_column_type(engine, column_name):
    """Check the data type of a column"""
    inspector = inspect(engine)
    columns = inspector.get_columns('filings')
    for col in columns:
        if col['name'] == column_name:
            return str(col['type'])
    return None

def fix_empty_json_fields_safe():
    """Fix empty JSON fields in filings table - safe version that checks column existence"""
    
    # Create database connection
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        print("Starting to fix empty JSON fields in filings table...")
        print("=" * 60)
        
        # Get existing columns
        existing_columns = get_existing_columns(engine)
        print(f"Found {len(existing_columns)} columns in filings table")
        
        # Define columns to check
        json_columns_to_check = [
            'financial_metrics',
            'financial_highlights', 
            'core_metrics',
            'smart_markup_data',
            'analyst_expectations',
            'key_points',
            'risks', 
            'opportunities',
            'annual_risk_assessment',
            'quarterly_performance',
            'quarterly_vs_expectations',
            'required_actions',
            'ipo_risk_factors',
            'event_items',
            'extracted_sections',
            'table_of_contents',
            'financial_data'
        ]
        
        # Filter to only existing columns
        columns_to_fix = [col for col in json_columns_to_check if col in existing_columns]
        missing_columns = [col for col in json_columns_to_check if col not in existing_columns]
        
        if missing_columns:
            print(f"\nColumns not found in database (will skip):")
            for col in missing_columns:
                print(f"  - {col}")
        
        print(f"\nColumns to check and fix:")
        for col in columns_to_fix:
            col_type = check_column_type(engine, col)
            print(f"  - {col} (type: {col_type})")
        
        print("\n" + "=" * 60)
        print("Running SQL updates for empty JSON fields...")
        
        total_updated = 0
        
        for column_name in columns_to_fix:
            col_type = check_column_type(engine, column_name)
            
            # Different queries depending on column type
            if 'JSON' in col_type.upper():
                # For JSON columns
                queries = [
                    f"UPDATE filings SET {column_name} = NULL WHERE {column_name}::text = '{{}}'",
                    f"UPDATE filings SET {column_name} = NULL WHERE {column_name}::text = '[]'"
                ]
            elif 'TEXT' in col_type.upper() or 'VARCHAR' in col_type.upper():
                # For TEXT columns
                queries = [
                    f"UPDATE filings SET {column_name} = NULL WHERE {column_name} = '{{}}'",
                    f"UPDATE filings SET {column_name} = NULL WHERE {column_name} = '[]'",
                    f"UPDATE filings SET {column_name} = NULL WHERE {column_name} = ''"
                ]
            else:
                print(f"  Skipping {column_name} - unknown type: {col_type}")
                continue
            
            for query in queries:
                try:
                    result = db.execute(text(query))
                    if result.rowcount > 0:
                        print(f"  ✓ Fixed {result.rowcount} rows in {column_name}")
                        total_updated += result.rowcount
                except Exception as e:
                    # Silently skip if the query fails (might be due to type mismatch)
                    pass
        
        # Also check for specific problematic patterns
        print("\nChecking for other problematic patterns...")
        
        # Fix financial_metrics if it exists
        if 'financial_metrics' in columns_to_fix:
            try:
                # Check if there are any rows with problematic data
                check_query = text("""
                    SELECT COUNT(*) as count 
                    FROM filings 
                    WHERE financial_metrics IS NOT NULL 
                    AND financial_metrics::text IN ('{}', '[]', '""')
                """)
                result = db.execute(check_query).fetchone()
                if result and result[0] > 0:
                    print(f"  Found {result[0]} rows with empty financial_metrics")
            except:
                pass
        
        # Commit all changes
        db.commit()
        print(f"\n✅ Completed! Fixed {total_updated} total fields")
        
        # Show summary of current state
        print("\n" + "=" * 60)
        print("Verification - Checking for remaining empty values...")
        
        for column_name in columns_to_fix[:5]:  # Check first 5 columns as sample
            try:
                col_type = check_column_type(engine, column_name)
                if 'JSON' in col_type.upper():
                    check_query = text(f"""
                        SELECT COUNT(*) as count 
                        FROM filings 
                        WHERE {column_name}::text IN ('{{}}', '[]')
                    """)
                else:
                    check_query = text(f"""
                        SELECT COUNT(*) as count 
                        FROM filings 
                        WHERE {column_name} IN ('{{}}', '[]', '')
                    """)
                    
                result = db.execute(check_query).fetchone()
                if result and result[0] > 0:
                    print(f"  ⚠️  {column_name}: Still has {result[0]} empty values")
                else:
                    print(f"  ✓ {column_name}: Clean")
            except Exception as e:
                print(f"  ? {column_name}: Could not check - {str(e)[:50]}")
        
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error occurred: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


def add_missing_columns():
    """Add any missing columns to the database"""
    
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        print("\nChecking for missing columns...")
        
        # Get existing columns
        existing_columns = get_existing_columns(engine)
        
        # Define columns that should exist (with their types)
        required_columns = {
            'core_metrics': 'TEXT',
            'financial_highlights': 'TEXT', 
            'financial_metrics': 'TEXT',
            'smart_markup_data': 'JSON',
            'analyst_expectations': 'JSON'
        }
        
        # Find missing columns
        missing = {k: v for k, v in required_columns.items() if k not in existing_columns}
        
        if missing:
            print(f"\nAdding {len(missing)} missing columns...")
            for col_name, col_type in missing.items():
                try:
                    query = text(f"ALTER TABLE filings ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                    db.execute(query)
                    print(f"  ✓ Added column: {col_name} ({col_type})")
                except Exception as e:
                    print(f"  ❌ Could not add {col_name}: {str(e)}")
            
            db.commit()
            print("\n✅ Missing columns added successfully")
        else:
            print("  ✓ All required columns already exist")
            
    except Exception as e:
        print(f"\n❌ Error adding columns: {str(e)}")
        db.rollback()
    finally:
        db.close()


def show_sample_data():
    """Show sample data to understand the current state"""
    
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        print("\n" + "=" * 60)
        print("Sample Data Check")
        print("=" * 60)
        
        # Get one sample filing
        query = text("""
            SELECT id, filing_type, 
                   financial_metrics,
                   financial_highlights
            FROM filings 
            WHERE filing_type = '10-Q'
            LIMIT 1
        """)
        
        result = db.execute(query).fetchone()
        if result:
            print(f"\nSample Filing ID {result[0]} ({result[1]}):")
            print(f"  financial_metrics: {str(result[2])[:100] if result[2] else 'NULL'}")
            print(f"  financial_highlights: {str(result[3])[:100] if result[3] else 'NULL'}")
        else:
            print("\nNo filings found in database")
            
    except Exception as e:
        print(f"\nCould not fetch sample data: {str(e)}")
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Filing Fields Fix Script (Safe Version)")
    print("=" * 60)
    
    # Step 1: Add missing columns if needed
    add_missing_columns()
    
    # Step 2: Fix empty JSON fields
    fix_empty_json_fields_safe()
    
    # Step 3: Show sample data
    show_sample_data()
    
    print("\n✅ Script completed successfully!")
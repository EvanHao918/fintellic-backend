#!/usr/bin/env python3
"""
Fix database issues - 一次性修复所有数据库问题
Run this script to fix:
1. Missing ticker fields
2. Status enum case inconsistencies
3. Empty JSON fields
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import SessionLocal, engine
from app.models import Filing, Company
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def fix_missing_tickers():
    """修复缺失的ticker字段"""
    logger.info("Fixing missing tickers...")
    db = SessionLocal()
    
    try:
        # SQL方式更新（更高效）
        result = db.execute(text("""
            UPDATE filings 
            SET ticker = companies.ticker 
            FROM companies 
            WHERE filings.company_id = companies.id 
            AND (filings.ticker IS NULL OR filings.ticker = '')
            AND companies.ticker IS NOT NULL
        """))
        
        db.commit()
        logger.info(f"Updated {result.rowcount} filings with ticker information")
        
    except Exception as e:
        logger.error(f"Error fixing tickers: {e}")
        db.rollback()
    finally:
        db.close()


def fix_status_enum_case():
    """修复状态枚举大小写问题"""
    logger.info("Fixing status enum case issues...")
    db = SessionLocal()
    
    try:
        # 统一改为大写（与枚举定义一致）
        status_mappings = {
            'pending': 'PENDING',
            'downloading': 'DOWNLOADING', 
            'parsing': 'PARSING',
            'analyzing': 'ANALYZING',
            'completed': 'COMPLETED',
            'failed': 'FAILED',
            'skipped': 'SKIPPED'
        }
        
        for old_status, new_status in status_mappings.items():
            result = db.execute(text(f"""
                UPDATE filings 
                SET status = :new_status 
                WHERE LOWER(status::text) = :old_status
            """), {"new_status": new_status, "old_status": old_status})
            
            if result.rowcount > 0:
                logger.info(f"Updated {result.rowcount} filings from {old_status} to {new_status}")
        
        db.commit()
        
    except Exception as e:
        logger.error(f"Error fixing status enum: {e}")
        db.rollback()
    finally:
        db.close()


def fix_empty_json_fields():
    """修复空的JSON字段"""
    logger.info("Fixing empty JSON fields...")
    db = SessionLocal()
    
    try:
        # 将空的JSON对象设置为NULL
        json_fields = [
            'financial_metrics',
            'financial_highlights', 
            'smart_markup_data',
            'analyst_expectations',
            'extracted_sections',
            'table_of_contents',
            'financial_data',
            'event_items',
            'key_points',
            'risks',
            'opportunities'
        ]
        
        for field in json_fields:
            try:
                result = db.execute(text(f"""
                    UPDATE filings 
                    SET {field} = NULL 
                    WHERE {field}::text = '{{}}'
                """))
                
                if result.rowcount > 0:
                    logger.info(f"Cleaned {result.rowcount} empty {field} fields")
            except:
                # Field might not exist in all deployments
                pass
        
        db.commit()
        
    except Exception as e:
        logger.error(f"Error fixing JSON fields: {e}")
        db.rollback()
    finally:
        db.close()


def add_missing_enum_values():
    """确保所有枚举值都存在"""
    logger.info("Checking and adding missing enum values...")
    
    try:
        with engine.connect() as conn:
            # 检查现有的枚举值
            result = conn.execute(text("""
                SELECT enumlabel 
                FROM pg_enum 
                WHERE enumtypid = (
                    SELECT oid FROM pg_type WHERE typname = 'processingstatus'
                )
            """))
            
            existing_values = {row[0] for row in result}
            logger.info(f"Existing enum values: {existing_values}")
            
            # 需要的枚举值（大写）
            required_values = {
                'PENDING', 'DOWNLOADING', 'PARSING', 
                'ANALYZING', 'COMPLETED', 'FAILED', 'SKIPPED'
            }
            
            missing_values = required_values - existing_values
            
            if missing_values:
                for value in missing_values:
                    try:
                        conn.execute(text(f"""
                            ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS '{value}'
                        """))
                        logger.info(f"Added missing enum value: {value}")
                    except Exception as e:
                        logger.warning(f"Could not add {value}: {e}")
                conn.commit()
            else:
                logger.info("All required enum values already exist")
                
    except Exception as e:
        logger.error(f"Error checking enum values: {e}")


def verify_fixes():
    """验证修复结果"""
    logger.info("\n" + "="*50)
    logger.info("Verifying fixes...")
    
    db = SessionLocal()
    try:
        # 检查ticker
        missing_ticker_count = db.execute(text("""
            SELECT COUNT(*) FROM filings 
            WHERE (ticker IS NULL OR ticker = '')
            AND company_id IN (SELECT id FROM companies WHERE ticker IS NOT NULL)
        """)).scalar()
        
        logger.info(f"Filings still missing ticker: {missing_ticker_count}")
        
        # 检查状态分布
        status_dist = db.execute(text("""
            SELECT status, COUNT(*) as count 
            FROM filings 
            GROUP BY status 
            ORDER BY count DESC
        """)).fetchall()
        
        logger.info("Status distribution:")
        for status, count in status_dist:
            logger.info(f"  {status}: {count}")
        
        # 检查最近的财报
        recent_filings = db.execute(text("""
            SELECT f.id, c.ticker, f.filing_type, f.status, f.filing_date
            FROM filings f
            JOIN companies c ON f.company_id = c.id
            WHERE f.status = 'COMPLETED'
            ORDER BY f.filing_date DESC
            LIMIT 5
        """)).fetchall()
        
        logger.info("\nMost recent completed filings:")
        for filing in recent_filings:
            logger.info(f"  ID:{filing[0]} {filing[1]} {filing[2]} {filing[3]} {filing[4]}")
            
    except Exception as e:
        logger.error(f"Error during verification: {e}")
    finally:
        db.close()


def main():
    """主函数"""
    logger.info("Starting database fixes...")
    logger.info("="*50)
    
    # 执行修复
    add_missing_enum_values()
    fix_status_enum_case()
    fix_missing_tickers()
    fix_empty_json_fields()
    
    # 验证结果
    verify_fixes()
    
    logger.info("\n" + "="*50)
    logger.info("✅ Database fixes completed!")
    logger.info("Please restart the API service to ensure all changes take effect.")


if __name__ == "__main__":
    main()
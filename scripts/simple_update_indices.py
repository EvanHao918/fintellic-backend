#!/usr/bin/env python3
"""
Simple script to update company indices field based on boolean flags
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models import Company
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Update indices for all companies"""
    db: Session = SessionLocal()
    
    try:
        # Get all companies
        companies = db.query(Company).all()
        logger.info(f"Found {len(companies)} companies in database")
        
        updated_count = 0
        
        for company in companies:
            # Use the model's update_indices method
            old_indices = company.indices
            company.update_indices()
            
            if old_indices != company.indices:
                updated_count += 1
                logger.info(f"Updated {company.ticker}: {company.indices}")
        
        # Commit changes
        db.commit()
        
        # Show statistics
        logger.info("=" * 50)
        logger.info(f"Update complete!")
        logger.info(f"Total companies: {len(companies)}")
        logger.info(f"Updated: {updated_count}")
        
        # Count by category
        sp500_only = db.query(Company).filter(
            Company.is_sp500 == True,
            Company.is_nasdaq100 == False
        ).count()
        
        nasdaq_only = db.query(Company).filter(
            Company.is_sp500 == False,
            Company.is_nasdaq100 == True
        ).count()
        
        both_indices = db.query(Company).filter(
            Company.is_sp500 == True,
            Company.is_nasdaq100 == True
        ).count()
        
        logger.info(f"S&P 500 only: {sp500_only}")
        logger.info(f"NASDAQ 100 only: {nasdaq_only}")
        logger.info(f"Both indices: {both_indices}")
        logger.info("=" * 50)
        
        # Show examples
        logger.info("\nExample companies:")
        examples = db.query(Company).filter(
            Company.indices.isnot(None)
        ).limit(20).all()
        
        for company in examples:
            logger.info(f"  {company.ticker}: {company.indices}")
            
    except Exception as e:
        logger.error(f"Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("Updating company indices...")
    main()
    logger.info("✅ Done!")
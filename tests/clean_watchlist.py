#!/usr/bin/env python3
"""
Clear watchlist for test user

Run: python scripts/clear_test_watchlist.py
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models import User, Watchlist
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clear_test_watchlist():
    """Clear watchlist for test user"""
    db = SessionLocal()
    
    try:
        # Find test user
        test_user = db.query(User).filter(
            User.email == "test2@fintellic.com"
        ).first()
        
        if not test_user:
            logger.error("Test user not found")
            return
        
        # Delete all watchlist entries
        count = db.query(Watchlist).filter(
            Watchlist.user_id == test_user.id
        ).count()
        
        db.query(Watchlist).filter(
            Watchlist.user_id == test_user.id
        ).delete()
        
        db.commit()
        
        logger.info(f"Cleared {count} entries from test user's watchlist")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    clear_test_watchlist()
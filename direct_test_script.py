#!/usr/bin/env python3
"""
Direct test of view limits - minimal dependencies
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.user import User
from app.models.filing import Filing
from app.services.view_tracking import ViewTrackingService

def test_view_limits_directly():
    """Test view limits directly without API"""
    db = SessionLocal()
    
    try:
        print("=== Direct Test of View Tracking Service ===\n")
        
        # Get a free user
        user = db.query(User).filter(User.email == "test2@fintellic.com").first()
        if not user:
            print("User test2@fintellic.com not found")
            return
            
        print(f"Testing with user: {user.email} (Tier: {user.tier})")
        
        # Get completed filings
        filings = db.query(Filing).filter(Filing.status == "COMPLETED").order_by(Filing.id).all()
        print(f"Found {len(filings)} completed filings\n")
        
        if len(filings) < 4:
            print("Need at least 4 filings to test properly")
            return
        
        # Test viewing each filing
        for i, filing in enumerate(filings[:5]):
            print(f"\n--- Attempt {i+1}: Filing ID {filing.id} ---")
            
            # Check if can view
            check_result = ViewTrackingService.can_view_filing(db, user, filing.id)
            print(f"Can view: {check_result['can_view']}")
            print(f"Reason: {check_result['reason']}")
            print(f"Views today: {check_result['views_today']}")
            print(f"Views remaining: {check_result['views_remaining']}")
            
            if check_result['can_view']:
                # Record the view
                ViewTrackingService.record_view(db, user, filing.id)
                print("✅ View recorded")
            else:
                print("❌ View blocked - limit reached!")
                break
        
        # Get final stats
        print("\n--- Final Stats ---")
        final_stats = ViewTrackingService.get_user_view_stats(db, user.id)
        print(f"Total views today: {final_stats['views_today']}")
        print(f"Daily limit: {final_stats['daily_limit']}")
        print(f"Views remaining: {final_stats['views_remaining']}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_view_limits_directly()
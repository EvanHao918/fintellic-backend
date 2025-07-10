from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.user import User, UserTier
from app.models.user_filing_view import UserFilingView
from app.models.filing import Filing


class ViewTrackingService:
    """Service to track and enforce daily viewing limits for free users"""
    
    DAILY_FREE_LIMIT = 3
    
    @staticmethod
    def can_view_filing(db: Session, user: User, filing_id: int) -> dict:
        """
        Check if user can view a filing based on their tier and daily limits
        
        Returns:
            dict: {
                "can_view": bool,
                "reason": str,
                "views_today": int,
                "views_remaining": int,
                "is_pro": bool
            }
        """
        # Pro users have unlimited access
        if user.tier == UserTier.PRO:
            return {
                "can_view": True,
                "reason": "Pro user - unlimited access",
                "views_today": 0,
                "views_remaining": -1,  # -1 means unlimited
                "is_pro": True
            }
        
        # Check if user has already viewed this filing today
        today = date.today()
        existing_view = db.query(UserFilingView).filter(
            and_(
                UserFilingView.user_id == user.id,
                UserFilingView.filing_id == filing_id,
                UserFilingView.view_date == today
            )
        ).first()
        
        if existing_view:
            # User already viewed this filing today, don't count it again
            views_today = ViewTrackingService._get_views_today(db, user.id)
            return {
                "can_view": True,
                "reason": "Already viewed today",
                "views_today": views_today,
                "views_remaining": max(0, ViewTrackingService.DAILY_FREE_LIMIT - views_today),
                "is_pro": False
            }
        
        # Get today's view count
        views_today = ViewTrackingService._get_views_today(db, user.id)
        
        # Check if limit reached
        if views_today >= ViewTrackingService.DAILY_FREE_LIMIT:
            return {
                "can_view": False,
                "reason": "Daily limit reached",
                "views_today": views_today,
                "views_remaining": 0,
                "is_pro": False
            }
        
        # User can view
        return {
            "can_view": True,
            "reason": "Within daily limit",
            "views_today": views_today,
            "views_remaining": ViewTrackingService.DAILY_FREE_LIMIT - views_today,
            "is_pro": False
        }
    
    @staticmethod
    def record_view(db: Session, user: User, filing_id: int) -> bool:
        """
        Record that a user viewed a filing
        
        Returns:
            bool: True if view was recorded, False if already viewed today
        """
        today = date.today()
        
        # Check if already viewed today
        existing_view = db.query(UserFilingView).filter(
            and_(
                UserFilingView.user_id == user.id,
                UserFilingView.filing_id == filing_id,
                UserFilingView.view_date == today
            )
        ).first()
        
        if existing_view:
            return False
        
        # Record the view
        new_view = UserFilingView(
            user_id=user.id,
            filing_id=filing_id,
            viewed_at=datetime.utcnow(),
            view_date=today
        )
        db.add(new_view)
        
        # Update user's daily count cache
        if user.last_view_date != today:
            user.last_view_date = today
            user.daily_view_count = 1
        else:
            user.daily_view_count = (user.daily_view_count or 0) + 1
        
        db.commit()
        return True
    
    @staticmethod
    def get_user_view_stats(db: Session, user_id: int) -> dict:
        """Get viewing statistics for a user"""
        today = date.today()
        views_today = ViewTrackingService._get_views_today(db, user_id)
        
        user = db.query(User).filter(User.id == user_id).first()
        is_pro = user.tier == UserTier.PRO if user else False
        
        return {
            "views_today": views_today,
            "daily_limit": ViewTrackingService.DAILY_FREE_LIMIT if not is_pro else -1,
            "views_remaining": max(0, ViewTrackingService.DAILY_FREE_LIMIT - views_today) if not is_pro else -1,
            "is_pro": is_pro,
            "limit_reset_time": "00:00 UTC"  # Daily reset at midnight UTC
        }
    
    @staticmethod
    def _get_views_today(db: Session, user_id: int) -> int:
        """Get the number of unique filings viewed today by a user"""
        today = date.today()
        count = db.query(UserFilingView).filter(
            and_(
                UserFilingView.user_id == user_id,
                UserFilingView.view_date == today
            )
        ).count()
        return count
"""
View tracking service for implementing daily report limits
Tracks user views and enforces free tier limitations
FIXED: 统一Pro用户判断逻辑，确保返回一致的数据格式
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List, Set
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, Date
import pytz
from app.models.user import User, UserTier
from app.models.filing import Filing
from app.models.user_filing_view import UserFilingView
from app.core.cache import cache


class ViewTrackingService:
    """Service for tracking and limiting user filing views"""
    
    # Free tier daily limit
    DAILY_FREE_LIMIT = 2  # 每日限制2份
    
    # EST timezone (UTC-5)
    EST_TZ = pytz.timezone('US/Eastern')
    
    @classmethod
    def get_est_date(cls) -> datetime:
        """Get current date in EST timezone"""
        now = datetime.now(cls.EST_TZ)
        return now.date()
    
    @classmethod
    def get_est_midnight(cls) -> datetime:
        """Get next midnight in EST timezone"""
        now = datetime.now(cls.EST_TZ)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return midnight
    
    @classmethod
    def _is_pro_user(cls, user: User) -> bool:
        """
        统一的Pro用户判断逻辑
        检查多个条件以确保正确识别Pro用户
        """
        return (
            user.tier == UserTier.PRO or  # 枚举比较
            user.tier == 'PRO' or  # 字符串比较（兼容性）
            user.is_subscription_active == True or  # 订阅激活状态
            (hasattr(user, 'is_pro') and user.is_pro)  # is_pro属性
        )
    
    @classmethod
    def get_user_views_today(cls, db: Session, user_id: int) -> Dict[str, any]:
        """
        Get user's views for today in EST timezone
        Returns dict with view details
        """
        # Get today's date in EST
        today_est = cls.get_est_date()
        
        # Query views for today
        views_today = db.query(UserFilingView).filter(
            and_(
                UserFilingView.user_id == user_id,
                func.date(UserFilingView.view_date) == today_est
            )
        ).all()
        
        # Get unique filing IDs viewed today
        unique_filing_ids = list(set([view.filing_id for view in views_today]))
        
        # Get the actual filing IDs that have been viewed (for repeated access)
        viewed_filings = []
        for view in views_today:
            if view.filing_id not in [v['id'] for v in viewed_filings]:
                filing = db.query(Filing).filter(Filing.id == view.filing_id).first()
                if filing:
                    viewed_filings.append({
                        'id': filing.id,
                        'ticker': filing.ticker,
                        'type': filing.filing_type.value,
                        'viewed_at': view.viewed_at
                    })
        
        return {
            'date': today_est,
            'total_views': len(views_today),  # Total view count (including repeats)
            'unique_filings_viewed': len(unique_filing_ids),  # Unique filings viewed
            'filing_ids': unique_filing_ids,  # List of unique filing IDs
            'filings': viewed_filings,  # Filing details
            'next_reset': cls.get_est_midnight()  # Next reset time
        }
    
    @classmethod
    def can_view_filing(cls, db: Session, user: User, filing_id: int) -> Dict[str, any]:
        """
        Check if user can view a filing based on their tier and daily limits
        
        Returns:
            Dict with can_view (bool), reason (str), and additional info
        """
        # 🔥 关键修复：使用统一的Pro用户判断
        is_pro = cls._is_pro_user(user)
        
        # Pro users have unlimited access
        if is_pro:
            return {
                'can_view': True,
                'reason': 'Pro user - unlimited access',
                'is_pro': True,
                'views_today': 0,
                'views_remaining': -1,  # Unlimited
                'daily_limit': -1  # Unlimited
            }
        
        # Get today's views for Free users
        views_data = cls.get_user_views_today(db, user.id)
        unique_count = views_data['unique_filings_viewed']
        viewed_filing_ids = views_data['filing_ids']
        
        # Check if this filing was already viewed today (allow re-viewing)
        if filing_id in viewed_filing_ids:
            return {
                'can_view': True,
                'reason': 'Already viewed today - no additional charge',
                'is_pro': False,
                'views_today': unique_count,
                'views_remaining': max(0, cls.DAILY_FREE_LIMIT - unique_count),
                'daily_limit': cls.DAILY_FREE_LIMIT
            }
        
        # Check if limit reached
        if unique_count >= cls.DAILY_FREE_LIMIT:
            return {
                'can_view': False,
                'reason': 'Daily limit reached',
                'is_pro': False,
                'views_today': unique_count,
                'views_remaining': 0,
                'daily_limit': cls.DAILY_FREE_LIMIT
            }
        
        # User can view
        return {
            'can_view': True,
            'reason': 'Within daily limit',
            'is_pro': False,
            'views_today': unique_count,
            'views_remaining': cls.DAILY_FREE_LIMIT - unique_count,
            'daily_limit': cls.DAILY_FREE_LIMIT
        }
    
    @classmethod
    def record_view(cls, db: Session, user: User, filing_id: int) -> bool:
        """
        Record that a user viewed a filing
        
        Returns:
            bool: True if view was recorded, False if already viewed today
        """
        # Pro users don't need to record views for limiting
        if cls._is_pro_user(user):
            return True
        
        today_est = cls.get_est_date()
        
        # Check if already viewed today
        existing_view = db.query(UserFilingView).filter(
            and_(
                UserFilingView.user_id == user.id,
                UserFilingView.filing_id == filing_id,
                func.date(UserFilingView.view_date) == today_est
            )
        ).first()
        
        if existing_view:
            return False  # Already viewed today
        
        # Record the view
        new_view = UserFilingView(
            user_id=user.id,
            filing_id=filing_id,
            viewed_at=datetime.now(cls.EST_TZ),
            view_date=today_est
        )
        db.add(new_view)
        
        # Update user's daily count cache (optional optimization)
        if user.last_view_date != today_est:
            user.last_view_date = today_est
            user.daily_view_count = 1
        else:
            user.daily_view_count = (user.daily_view_count or 0) + 1
        
        db.commit()
        return True
    
    @classmethod
    def get_user_view_stats(cls, db: Session, user_id: int) -> Dict[str, any]:
        """
        Get viewing statistics for a user
        
        Returns:
            Dict with today's views, limits, and remaining views
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {
                'views_today': 0,
                'daily_limit': cls.DAILY_FREE_LIMIT,
                'views_remaining': cls.DAILY_FREE_LIMIT,
                'is_pro': False,
                'next_reset': cls.get_est_midnight()
            }
        
        # 🔥 关键修复：使用统一的Pro用户判断
        is_pro = cls._is_pro_user(user)
        
        if is_pro:
            # Pro用户返回特殊值表示无限制
            return {
                'views_today': 0,
                'daily_limit': -1,  # -1 表示无限制
                'views_remaining': -1,  # -1 表示无限制
                'is_pro': True,
                'next_reset': None
            }
        
        # Get today's views for free users
        views_data = cls.get_user_views_today(db, user_id)
        unique_count = views_data['unique_filings_viewed']
        
        return {
            'views_today': unique_count,
            'daily_limit': cls.DAILY_FREE_LIMIT,
            'views_remaining': max(0, cls.DAILY_FREE_LIMIT - unique_count),
            'is_pro': False,
            'next_reset': cls.get_est_midnight()
        }
    
    @classmethod
    def reset_daily_counts(cls, db: Session) -> int:
        """
        Reset daily view counts for all users (for scheduled task)
        
        Returns:
            Number of users reset
        """
        today_est = cls.get_est_date()
        
        # Reset users whose last_view_date is before today
        users_to_reset = db.query(User).filter(
            User.last_view_date < today_est
        ).all()
        
        count = 0
        for user in users_to_reset:
            user.daily_view_count = 0
            count += 1
        
        if count > 0:
            db.commit()
        
        return count
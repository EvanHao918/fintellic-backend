# app/models/__init__.py
"""
Models module - Central import point for all database models
FIXED: Removed duplicate Company import that was causing circular dependency
"""
from app.models.base import Base
from app.models.user import User, UserTier
from app.models.company import Company  # Only import from company.py, not filing.py
from app.models.filing import Filing, FilingType, ProcessingStatus, ManagementTone
from app.models.earnings_calendar import EarningsCalendar, EarningsTime
from app.models.comment import Comment
from app.models.user_vote import UserVote, VoteType
from app.models.comment_vote import CommentVote
from app.models.watchlist import Watchlist
from app.models.user_filing_view import UserFilingView

__all__ = [
    "Base",
    "User",
    "UserTier", 
    "Company",
    "Filing",
    "FilingType",
    "ProcessingStatus",
    "ManagementTone",
    "EarningsCalendar",
    "EarningsTime",
    "Comment",
    "UserVote",
    "VoteType",
    "CommentVote",
    "Watchlist",
    "UserFilingView"
]
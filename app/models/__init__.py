# app/models/__init__.py
"""
Models module - Central import point for all database models
Phase 4 Update: Added notification models and fixed import order
FIXED: Correct imports based on actual file contents
"""

# 1. Base model MUST be imported first
from app.models.base import Base

# 2. Independent models (no foreign key dependencies)
from app.models.company import Company
from app.models.pricing_plan import PricingPlan

# 3. User model and enums
from app.models.user import User, UserTier, SubscriptionType, PricingTier

# 4. Models that depend on User (Phase 4 notification models)
from app.models.notification_settings import UserNotificationSettings, NotificationHistory

# 5. Models that depend on Company and/or User
from app.models.filing import Filing, FilingType, ProcessingStatus, ManagementTone
from app.models.watchlist import Watchlist
from app.models.subscription import Subscription
from app.models.payment_record import PaymentRecord, PaymentStatus  # PaymentStatus exists
from app.models.user_filing_view import UserFilingView
from app.models.earnings_calendar import EarningsCalendar

# 6. Models that depend on Filing
from app.models.comment import Comment
from app.models.comment_vote import CommentVote  # Only CommentVote, no VoteType here
from app.models.user_vote import UserVote, VoteType  # VoteType is here!

# Try to import optional enums that might exist
try:
    from app.models.subscription import SubscriptionStatus
except ImportError:
    SubscriptionStatus = None

try:
    from app.models.earnings_calendar import EarningsTime, EarningsStatus
except ImportError:
    EarningsTime = None
    EarningsStatus = None

__all__ = [
    # Base
    "Base",
    
    # Company
    "Company",
    
    # User and related
    "User",
    "UserTier",
    "SubscriptionType",
    "PricingTier",
    
    # Phase 4: Notification models
    "UserNotificationSettings",
    "NotificationHistory",
    
    # Filing and related
    "Filing",
    "FilingType",
    "ProcessingStatus",
    "ManagementTone",
    "UserFilingView",
    
    # Subscription and payment
    "Subscription",
    "PaymentRecord",
    "PaymentStatus",  # This exists
    "PricingPlan",
    
    # Earnings
    "EarningsCalendar",
    
    # Social features
    "Comment",
    "CommentVote",
    "UserVote",
    "VoteType",  # This exists in user_vote.py
    "Watchlist",
]

# Add optional imports to __all__ if they exist
if SubscriptionStatus:
    __all__.append("SubscriptionStatus")
if EarningsTime:
    __all__.append("EarningsTime")
if EarningsStatus:
    __all__.append("EarningsStatus")
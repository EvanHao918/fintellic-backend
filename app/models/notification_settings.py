"""
Notification Settings Model
Phase 4: HermeSpeed Push Notification System
OPTIMIZED: Simplified model, removed redundant fields, core functionality only
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Time, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class UserNotificationSettings(Base):
    """
    User notification settings model
    SIMPLIFIED: Core filing preferences only, removed redundant features
    """
    __tablename__ = "user_notification_settings"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign key to user
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    # CORE FILING NOTIFICATION SETTINGS ONLY
    filing_10k = Column(Boolean, default=True, nullable=False)  # Annual reports
    filing_10q = Column(Boolean, default=True, nullable=False)  # Quarterly reports
    filing_8k = Column(Boolean, default=True, nullable=False)   # Current reports
    filing_s1 = Column(Boolean, default=True, nullable=False)   # IPO filings
    watchlist_only = Column(Boolean, default=False, nullable=False)  # Watchlist scope
    
    # Master switch
    notification_enabled = Column(Boolean, default=True, nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="notification_settings")
    
    def __repr__(self):
        return f"<NotificationSettings(user_id={self.user_id}, enabled={self.notification_enabled})>"
    
    def should_send_filing_notification(self, filing_type: str, is_in_watchlist: bool = False) -> bool:
        """
        Determine if user should receive notification for specific filing type
        SIMPLIFIED: Core filing types only
        
        Args:
            filing_type: Filing type (10-K, 10-Q, 8-K, S-1)
            is_in_watchlist: Whether the company is in user's watchlist
            
        Returns:
            bool: Whether to send notification
        """
        # Master switch check
        if not self.notification_enabled:
            return False
        
        # Watchlist scope check
        if self.watchlist_only and not is_in_watchlist:
            return False
        
        # Filing type preference check
        filing_type_map = {
            '10-K': self.filing_10k,
            '10-Q': self.filing_10q,
            '8-K': self.filing_8k,
            'S-1': self.filing_s1,
        }
        
        return filing_type_map.get(filing_type, False)
    
    def get_enabled_filing_types(self) -> list:
        """Get list of enabled filing types"""
        enabled_types = []
        if self.filing_10k:
            enabled_types.append('10-K')
        if self.filing_10q:
            enabled_types.append('10-Q')
        if self.filing_8k:
            enabled_types.append('8-K')
        if self.filing_s1:
            enabled_types.append('S-1')
        return enabled_types
    
    def get_notification_summary(self) -> str:
        """Get human-readable summary of notification settings"""
        if not self.notification_enabled:
            return "Notifications disabled"
        
        enabled_types = self.get_enabled_filing_types()
        scope = "Watchlist only" if self.watchlist_only else "All companies"
        
        if not enabled_types:
            return f"{scope} • No filing types selected"
        
        return f"{scope} • {len(enabled_types)} filing type{'s' if len(enabled_types) > 1 else ''}"


class NotificationHistory(Base):
    """
    Notification history record
    SIMPLIFIED: Core tracking only, reduced complexity
    """
    __tablename__ = "notification_history"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # User reference
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Notification content
    notification_type = Column(String(50), nullable=False, index=True)  # filing_release, test
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    data = Column(JSON)  # Additional notification data
    
    # Status tracking
    status = Column(String(20), default='pending')  # pending, sent, failed
    sent_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    
    # FCM response (optional)
    fcm_message_id = Column(String(255))
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    # Relationships
    user = relationship("User", backref="notification_history")
    
    def __repr__(self):
        return f"<NotificationHistory(id={self.id}, type={self.notification_type}, status={self.status})>"
    
    @property
    def is_successful(self) -> bool:
        """Check if notification was successfully sent"""
        return self.status == 'sent' and self.sent_at is not None
    
    @property
    def display_time(self) -> str:
        """Get display-friendly time"""
        time_to_show = self.sent_at or self.created_at
        return time_to_show.strftime('%Y-%m-%d %H:%M:%S UTC') if time_to_show else 'Unknown'
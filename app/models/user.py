from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.models.base import Base


class UserTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    
    
class User(Base):
    __tablename__ = "users"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Authentication fields
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Nullable for social auth
    
    # User information
    full_name = Column(String(255))
    username = Column(String(50), unique=True, index=True)
    avatar_url = Column(String(512))  # For social auth profile pictures
    
    # Social authentication IDs
    apple_user_id = Column(String(255), unique=True, index=True, nullable=True)
    google_user_id = Column(String(255), unique=True, index=True, nullable=True)
    linkedin_user_id = Column(String(255), unique=True, index=True, nullable=True)
    
    # Subscription status
    tier = Column(Enum(UserTier), default=UserTier.FREE, nullable=False)
    subscription_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Account status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True))
    last_login_ip = Column(String(45))
    
    # Registration tracking
    registration_source = Column(String(50))  # email, apple, google, linkedin
    registration_device_type = Column(String(50))  # ios, android, web
    
    # Biometric settings (stored as JSON)
    biometric_settings = Column(String(512))  # {"face_id": true, "devices": [...]}
    
    # Device tokens for push notifications
    device_tokens = Column(String(2048))  # JSON array of device tokens
    
    # Daily limits for free users
    daily_reports_count = Column(Integer, default=0)
    daily_reports_reset_at = Column(DateTime(timezone=True))
    
    # Daily view tracking
    last_view_date = Column(Date, nullable=True)
    daily_view_count = Column(Integer, nullable=True, default=0)
    
    # Relationships
    comments = relationship("Comment", back_populates="user", cascade="all, delete-orphan", foreign_keys="Comment.user_id")
    votes = relationship("UserVote", back_populates="user", cascade="all, delete-orphan")
    watchlist = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    filing_views = relationship("UserFilingView", back_populates="user", cascade="all, delete-orphan")
    comment_votes = relationship("CommentVote", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', tier={self.tier})>"
    
    @property
    def is_pro(self):
        """Check if user is a pro subscriber"""
        return self.tier == UserTier.PRO
    
    @property
    def has_social_auth(self):
        """Check if user has any social authentication"""
        return bool(self.apple_user_id or self.google_user_id or self.linkedin_user_id)
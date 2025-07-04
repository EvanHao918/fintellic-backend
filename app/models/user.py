from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
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
    hashed_password = Column(String(255), nullable=False)
    
    # User information
    full_name = Column(String(255))
    username = Column(String(50), unique=True, index=True)
    
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
    
    # Daily limits for free users
    daily_reports_count = Column(Integer, default=0)
    daily_reports_reset_at = Column(DateTime(timezone=True))
    
    # Relationships
    comments = relationship("Comment", back_populates="user", cascade="all, delete-orphan")
    votes = relationship("UserVote", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', tier={self.tier})>"
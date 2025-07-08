"""
UserVote model for tracking user voting history
"""
from sqlalchemy import Column, Integer, ForeignKey, DateTime, String, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.models.base import Base


class VoteType(str, enum.Enum):
    """Vote sentiment types"""
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"


class UserVote(Base):
    """UserVote model for tracking which users voted on which filings"""
    __tablename__ = "user_votes"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filing_id = Column(Integer, ForeignKey("filings.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Vote information - 使用字符串而不是枚举
    vote_type = Column(String(10), nullable=False)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="votes")
    filing = relationship("Filing", back_populates="user_votes")
    
    # Unique constraint to prevent duplicate votes
    __table_args__ = (
        UniqueConstraint('user_id', 'filing_id', name='unique_user_filing_vote'),
    )
    
    def __repr__(self):
        return f"<UserVote(user_id={self.user_id}, filing_id={self.filing_id}, vote={self.vote_type})>"
    
    @classmethod
    def has_user_voted(cls, db_session, user_id: int, filing_id: int) -> bool:
        """Check if a user has already voted on a filing"""
        return db_session.query(cls).filter(
            cls.user_id == user_id,
            cls.filing_id == filing_id
        ).first() is not None
    
    @classmethod
    def get_user_vote(cls, db_session, user_id: int, filing_id: int):
        """Get a user's vote on a filing"""
        return db_session.query(cls).filter(
            cls.user_id == user_id,
            cls.filing_id == filing_id
        ).first()
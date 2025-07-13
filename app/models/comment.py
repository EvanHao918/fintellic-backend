"""
Comment model for user comments on filings
"""
from sqlalchemy import Column, Integer, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timezone, timedelta

from app.models.base import Base


class Comment(Base):
    """Comment model for storing user comments on filings"""
    __tablename__ = "comments"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    filing_id = Column(Integer, ForeignKey("filings.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Comment content
    content = Column(Text, nullable=False)
    
    # Vote counts (denormalized for performance)
    upvotes = Column(Integer, default=0, nullable=False)
    downvotes = Column(Integer, default=0, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    filing = relationship("Filing", back_populates="comments", foreign_keys=[filing_id])
    user = relationship("User", back_populates="comments", foreign_keys=[user_id])
    votes = relationship("CommentVote", back_populates="comment", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Comment(id={self.id}, user_id={self.user_id}, filing_id={self.filing_id})>"
    
    def is_editable(self, user_id: int) -> bool:
        """Check if comment can be edited by a user"""
        if self.user_id != user_id:
            return False
        
        if self.created_at:
            current_time = datetime.now(timezone.utc)
            if self.created_at.tzinfo is None:
                created_at_utc = self.created_at.replace(tzinfo=timezone.utc)
            else:
                created_at_utc = self.created_at
            
            if (current_time - created_at_utc) > timedelta(minutes=5):
                return False
        
        return True
    
    @property
    def net_votes(self) -> int:
        """Calculate net votes (upvotes - downvotes)"""
        return self.upvotes - self.downvotes
    
    def get_user_vote(self, user_id: int) -> int:
        """Get user's vote on this comment (1, -1, or 0)"""
        vote = next((v for v in self.votes if v.user_id == user_id), None)
        return vote.vote_type if vote else 0
"""
Comment model for user comments on filings
ENHANCED: Added reply support with comment preview (Simplified Design)
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
    
    # Reply field (SIMPLIFIED - only one field needed)
    reply_to_comment_id = Column(Integer, ForeignKey("comments.id", ondelete="SET NULL"), nullable=True, index=True)
    # REMOVED: reply_to_user_id - not needed, get from reply_to_comment.user
    
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
    
    # Reply relationships (SIMPLIFIED)
    reply_to_comment = relationship("Comment", remote_side=[id], foreign_keys=[reply_to_comment_id])
    replies = relationship("Comment", back_populates="reply_to_comment", foreign_keys=[reply_to_comment_id])
    # REMOVED: reply_to_user relationship - get via reply_to_comment.user
    
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
    
    def get_reply_preview(self, max_length: int = 50) -> str:
        """Get a preview of the comment content for reply display"""
        if not self.content:
            return ""
        
        if len(self.content) <= max_length:
            return self.content
        
        # Truncate at word boundary if possible
        truncated = self.content[:max_length]
        last_space = truncated.rfind(' ')
        if last_space > max_length * 0.7:  # If there's a space in the last 30% of the text
            truncated = truncated[:last_space]
        
        return truncated + "..."
    
    @property
    def reply_to_user(self):
        """Get the user being replied to via the parent comment"""
        if self.reply_to_comment:
            return self.reply_to_comment.user
        return None
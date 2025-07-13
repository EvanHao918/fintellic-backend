"""
Comment vote model for upvoting/downvoting comments
"""
from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint, CheckConstraint, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class CommentVote(Base):
    """Model for tracking user votes on comments"""
    __tablename__ = "comment_votes"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    comment_id = Column(Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=False)
    
    # Vote type: 1 for upvote, -1 for downvote
    vote_type = Column(Integer, nullable=False)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="comment_votes")
    comment = relationship("Comment", back_populates="votes")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'comment_id', name='unique_user_comment_vote'),
        CheckConstraint('vote_type IN (1, -1)', name='valid_vote_type'),
    )
    
    def __repr__(self):
        return f"<CommentVote(user_id={self.user_id}, comment_id={self.comment_id}, vote_type={self.vote_type})>"
"""
Comment model for user comments on filings
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

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
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.utcnow)
    
    # Relationships
    filing = relationship("Filing", back_populates="comments")
    user = relationship("User", back_populates="comments")
    
    def __repr__(self):
        return f"<Comment(id={self.id}, user_id={self.user_id}, filing_id={self.filing_id})>"
    
    @property
    def is_editable(self, user_id: int) -> bool:
        """Check if comment can be edited by a user"""
        # Comments can be edited by the author within 5 minutes
        from datetime import timedelta
        if self.user_id != user_id:
            return False
        if self.created_at and (datetime.utcnow() - self.created_at) > timedelta(minutes=5):
            return False
        return True
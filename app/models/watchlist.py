# app/models/watchlist.py
"""
Watchlist model for user's favorite companies
"""
from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.base import Base


class Watchlist(Base):
    """
    User watchlist entries
    Each entry represents a user watching a company
    """
    __tablename__ = "user_watchlist"
    
    # Composite primary key and unique constraint
    __table_args__ = (
        UniqueConstraint('user_id', 'company_id', name='_user_company_uc'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="watchlist")
    company = relationship("Company", back_populates="watchers")
    
    def __repr__(self):
        return f"<Watchlist(user_id={self.user_id}, company_id={self.company_id})>"
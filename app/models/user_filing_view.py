from sqlalchemy import Column, Integer, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.base import Base


class UserFilingView(Base):
    """Track user filing views for daily limit enforcement"""
    __tablename__ = "user_filing_views"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filing_id = Column(Integer, ForeignKey("filings.id"), nullable=False)
    viewed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    view_date = Column(Date, nullable=False, default=datetime.utcnow().date)
    
    # Relationships
    user = relationship("User", back_populates="filing_views")
    filing = relationship("Filing", back_populates="user_views")
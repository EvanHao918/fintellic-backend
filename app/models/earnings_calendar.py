# app/models/earnings_calendar.py
"""
Earnings Calendar model for tracking upcoming earnings announcements
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Boolean, Date, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.models.base import Base
import enum


class EarningsTime(str, enum.Enum):
    """When earnings will be announced"""
    BMO = "bmo"  # Before Market Open
    AMC = "amc"  # After Market Close
    TNS = "tns"  # Time Not Supplied
    

class EarningsCalendar(Base):
    """Earnings announcement schedule"""
    __tablename__ = "earnings_calendar"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign key
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    
    # Earnings date and time
    earnings_date = Column(Date, nullable=False, index=True)
    earnings_time = Column(SQLEnum(EarningsTime), default=EarningsTime.TNS)
    
    # Fiscal period
    fiscal_quarter = Column(String(10))  # e.g., "Q1 2025"
    fiscal_year = Column(Integer)
    
    # Estimates (from yfinance)
    eps_estimate = Column(Float)  # Earnings per share estimate
    revenue_estimate = Column(Float)  # Revenue estimate in millions
    
    # Previous results (for comparison)
    previous_eps = Column(Float)
    previous_revenue = Column(Float)
    
    # Status
    is_confirmed = Column(Boolean, default=False)  # Whether date is confirmed by company
    
    # Source and timestamps
    source = Column(String(50), default="yfinance")
    created_at = Column(DateTime, server_default="now()")
    updated_at = Column(DateTime, server_default="now()", onupdate="now()")
    
    # Relationships
    company = relationship("Company", back_populates="earnings_calendar")
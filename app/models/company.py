# app/models/company.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.base import Base


class Company(Base):
    __tablename__ = "companies"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # SEC identifiers
    cik = Column(String(10), unique=True, index=True, nullable=False)  # Central Index Key
    ticker = Column(String(10), unique=True, index=True, nullable=False)
    
    # Company information
    name = Column(String(255), nullable=False)
    legal_name = Column(String(255))
    
    # Classification
    sic = Column(String(10))  # Standard Industrial Classification
    sic_description = Column(String(255))
    
    # Location
    state = Column(String(2))
    state_of_incorporation = Column(String(2))
    
    # Business details
    fiscal_year_end = Column(String(4))  # MMDD format
    business_address = Column(Text)
    mailing_address = Column(Text)
    
    # Contact
    business_phone = Column(String(50))
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Market info
    exchange = Column(String(50))
    is_sp500 = Column(Boolean, default=False, nullable=False)
    is_nasdaq100 = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_filing_date = Column(DateTime(timezone=True))
    
    # Relationships (Day 8 addition)
    filings = relationship("Filing", back_populates="company")
    earnings_calendar = relationship("EarningsCalendar", back_populates="company")
    
    def __repr__(self):
        return f"<Company(id={self.id}, ticker='{self.ticker}', name='{self.name}')>"
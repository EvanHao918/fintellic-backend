from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.models.base import Base


class FilingType(str, enum.Enum):
    FORM_10K = "10-K"     # Annual report
    FORM_10Q = "10-Q"     # Quarterly report
    FORM_8K = "8-K"       # Current report
    FORM_S1 = "S-1"       # IPO registration
    FORM_DEF14A = "DEF 14A"  # Proxy statement
    FORM_20F = "20-F"     # Foreign annual report
    

class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PARSING = "parsing"
    AI_PROCESSING = "ai_processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ManagementTone(str, enum.Enum):
    OPTIMISTIC = "optimistic"
    CONFIDENT = "confident"
    NEUTRAL = "neutral"
    CAUTIOUS = "cautious"
    CONCERNED = "concerned"


class Filing(Base):
    __tablename__ = "filings"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign key
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    
    # SEC identifiers
    accession_number = Column(String(25), unique=True, index=True, nullable=False)
    filing_type = Column(Enum(FilingType), nullable=False, index=True)
    
    # Filing dates
    filing_date = Column(DateTime(timezone=True), nullable=False, index=True)
    period_date = Column(DateTime(timezone=True))  # Period end date
    
    # File information
    primary_doc_url = Column(String(500))
    primary_doc_description = Column(String(255))
    full_text_url = Column(String(500))
    
    # AI-generated content
    ai_summary = Column(Text)  # 5-minute summary
    management_tone = Column(Enum(ManagementTone))
    tone_explanation = Column(Text)
    key_tags = Column(JSON)  # Array of tags like ["RecordRevenue", "ChinaChallenges"]
    key_questions = Column(JSON)  # Q&A pairs
    key_quotes = Column(JSON)  # Important quotes from management
    
    # Financial highlights (if applicable)
    financial_highlights = Column(JSON)
    
    # Processing status
    status = Column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING, nullable=False)
    processing_started_at = Column(DateTime(timezone=True))
    processing_completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    
    # Community sentiment
    bullish_votes = Column(Integer, default=0)
    neutral_votes = Column(Integer, default=0)
    bearish_votes = Column(Integer, default=0)
    
    # Flags
    is_amended = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    company = relationship("Company", back_populates="filings")
    
    def __repr__(self):
        return f"<Filing(id={self.id}, type={self.filing_type}, company_id={self.company_id})>"
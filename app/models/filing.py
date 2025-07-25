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
    
    # New columns added in Day 10.5
    event_type = Column(String(100), nullable=True)  # For 8-K event types
    comment_count = Column(Integer, default=0, nullable=False)
    
    # New fields for differentiated display (Day 15+ addition)
    filing_specific_data = Column(JSON, default={})
    chart_data = Column(JSON, default={})  # Pre-processed chart data
    
    # ==================== NEW FIELDS FOR DIFFERENTIATED DISPLAY (Day 19) ====================
    
    # 10-K Specific Fields
    auditor_opinion = Column(Text)  # Auditor's opinion text
    three_year_financials = Column(Text)  # ✅ CHANGED FROM JSON TO TEXT
    business_segments = Column(Text)  # ✅ CHANGED FROM JSON TO TEXT
    risk_summary = Column(Text)  # ✅ CHANGED FROM JSON TO TEXT
    growth_drivers = Column(Text)  # GPT: Growth analysis
    management_outlook = Column(Text)  # GPT: Management outlook
    strategic_adjustments = Column(Text)  # GPT: Strategic changes
    market_impact_10k = Column(Text)  # GPT: 10-K 潜在市场影响
    
    # 10-Q Specific Fields
    expectations_comparison = Column(Text)  # ✅ CHANGED FROM JSON TO TEXT
    cost_structure = Column(Text)  # ✅ CHANGED FROM JSON TO TEXT
    guidance_update = Column(Text)  # ✅ CHANGED FROM JSON TO TEXT
    growth_decline_analysis = Column(Text)  # GPT: Growth/decline drivers
    management_tone_analysis = Column(Text)  # GPT: Tone analysis
    beat_miss_analysis = Column(Text)  # GPT: Beat/miss reasons
    market_impact_10q = Column(Text)  # GPT: 10-Q 潜在市场影响
    
    # 8-K Specific Fields
    item_type = Column(String(10))  # e.g., "5.02", "1.01"
    items = Column(Text)  # ✅ CHANGED FROM JSON TO TEXT
    event_timeline = Column(Text)  # ✅ CHANGED FROM JSON TO TEXT
    event_nature_analysis = Column(Text)  # GPT: Event nature
    market_impact_analysis = Column(Text)  # GPT: Market impact
    key_considerations = Column(Text)  # GPT: Key points
    
    # S-1 Specific Fields
    ipo_details = Column(Text)  # ✅ CHANGED FROM JSON TO TEXT
    company_overview = Column(Text)  # Business description
    financial_summary = Column(Text)  # ✅ CHANGED FROM JSON TO TEXT
    risk_categories = Column(Text)  # ✅ CHANGED FROM JSON TO TEXT
    growth_path_analysis = Column(Text)  # GPT: Growth path
    competitive_moat_analysis = Column(Text)  # GPT: Competitive advantage
    
    # Common fields
    fiscal_year = Column(String(10))  # e.g., "2024"
    fiscal_quarter = Column(String(10))  # e.g., "Q3 2024"
    period_end_date = Column(DateTime(timezone=True))  # Period end date
    
    # Relationships
    company = relationship("Company", back_populates="filings")
    comments = relationship("Comment", back_populates="filing", cascade="all, delete-orphan")
    user_votes = relationship("UserVote", back_populates="filing", cascade="all, delete-orphan")
    user_views = relationship("UserFilingView", back_populates="filing", cascade="all, delete-orphan")
    
    @property
    def get_specific_data(self):
        """Return structured data based on form_type"""
        if self.filing_type == FilingType.FORM_10K:
            return self.filing_specific_data.get("10k_data", {})
        elif self.filing_type == FilingType.FORM_10Q:
            return self.filing_specific_data.get("10q_data", {})
        elif self.filing_type == FilingType.FORM_8K:
            return self.filing_specific_data.get("8k_data", {})
        elif self.filing_type == FilingType.FORM_S1:
            return self.filing_specific_data.get("s1_data", {})
        else:
            return {}
    
    def __repr__(self):
        return f"<Filing(id={self.id}, type={self.filing_type}, company_id={self.company_id})>"
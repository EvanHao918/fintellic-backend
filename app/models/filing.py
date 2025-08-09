"""
Filing model - Core model for SEC filings
FIXED: Changed financial_metrics and other JSON fields to Text to avoid type conflicts
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum as SQLEnum, JSON, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
import json
from app.models.base import Base


class FilingType(enum.Enum):
    """Types of SEC filings we process"""
    FORM_10K = "10-K"      # Annual report
    FORM_10Q = "10-Q"      # Quarterly report
    FORM_8K = "8-K"        # Current report
    FORM_S1 = "S-1"        # IPO registration
    FORM_S1_A = "S-1/A"    # IPO amendment
    FORM_424B4 = "424B4"   # IPO prospectus
    FORM_DEF14A = "DEF 14A"  # Proxy statement
    FORM_20F = "20-F"      # Foreign annual report
    OTHER = "OTHER"


class ProcessingStatus(enum.Enum):
    """Filing processing status"""
    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"
    PARSING = "PARSING"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ManagementTone(enum.Enum):
    """Management tone assessment"""
    VERY_OPTIMISTIC = "very_optimistic"
    OPTIMISTIC = "optimistic"
    CONFIDENT = "confident"
    CONCERNED = "concerned"  # 添加这个缺失的值
    NEUTRAL = "neutral"
    CAUTIOUS = "cautious"
    PESSIMISTIC = "pessimistic"


class Filing(Base):
    __tablename__ = "filings"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Company reference
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    ticker = Column(String(10), index=True)  # Denormalized for performance
    
    # Filing identifiers
    accession_number = Column(String(25), unique=True, index=True, nullable=False)
    filing_type = Column(SQLEnum(FilingType), nullable=False, index=True)
    form_type = Column(String(20))  # Raw form type from SEC
    
    # Filing dates
    filing_date = Column(DateTime(timezone=True), nullable=False, index=True)
    period_end_date = Column(DateTime(timezone=True))
    accepted_date = Column(DateTime(timezone=True))
    
    # URLs
    filing_url = Column(String(500))
    primary_document_url = Column(String(500))
    interactive_data_url = Column(String(500))
    
    primary_doc_url = Column(String(500))  # Old field name in database
    full_text_url = Column(String(500))  # Old field name in database
    
    # Processing status
    status = Column(SQLEnum(ProcessingStatus), default=ProcessingStatus.PENDING, nullable=False, index=True)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # Processing timestamps
    processing_started_at = Column(DateTime(timezone=True))
    processing_completed_at = Column(DateTime(timezone=True))
    download_completed_at = Column(DateTime(timezone=True))
    parsing_completed_at = Column(DateTime(timezone=True))
    analysis_completed_at = Column(DateTime(timezone=True))
    
    # Content storage
    raw_text = Column(Text)  # Full text content
    raw_text_size = Column(Integer)  # Size in bytes
    primary_doc_html = Column(Text)  # HTML of primary document
    
    # Extracted sections
    extracted_sections = Column(JSON)  # JSON with section names and content
    table_of_contents = Column(JSON)  # JSON array of TOC items
    
    # Financial data (for 10-K and 10-Q)
    financial_data = Column(JSON)  # Extracted financial statements
    revenue = Column(Float)  # Latest revenue (millions)
    net_income = Column(Float)  # Latest net income (millions)
    eps = Column(Float)  # Earnings per share
    
    # For quarterly reports (10-Q) - Analyst expectations
    expected_eps = Column(Float)  # Analyst consensus EPS
    expected_revenue = Column(Float)  # Analyst consensus revenue (millions)
    eps_surprise = Column(Float)  # Actual vs expected EPS
    revenue_surprise = Column(Float)  # Actual vs expected revenue
    
    # Event information (for 8-K)
    event_items = Column(JSON)  # Array of item numbers reported
    event_type = Column(String(100))  # Main event type
    event_description = Column(Text)
    
    # IPO specific (for S-1)
    ipo_price_range_low = Column(Float)
    ipo_price_range_high = Column(Float)
    ipo_shares_offered = Column(Integer)
    ipo_use_of_proceeds = Column(Text)
    
    # AI Analysis results - Unified fields for all filing types
    analysis_version = Column(String(10), default="v5")  # Track analysis version
    
    # Core unified fields (present in all filing types)
    unified_analysis = Column(Text)  # Main AI analysis with structure
    unified_feed_summary = Column(String(100))  # 50-80 char summary for feed
    key_tags = Column(JSON)
    unified_score = Column(Integer)  # 1-100 overall score
    
    # Common analysis fields
    key_points = Column(JSON)  # Array of key points
    risks = Column(JSON)  # Array of identified risks
    opportunities = Column(JSON)  # Array of opportunities
    
    # Sentiment and tone
    sentiment_score = Column(Float)  # -1 to 1
    management_tone = Column(SQLEnum(ManagementTone))
    
    # Market context
    market_reaction_prediction = Column(Text)
    competitive_positioning = Column(Text)
    
    # ============= Financial metrics fields =============
    # Keep as JSON since database has them as JSON
    financial_metrics = Column(JSON)  # Key financial metrics
    financial_highlights = Column(JSON)  # Financial highlights
    core_metrics = Column(Text)  # Core metrics for 10-Q (newly added as TEXT)
    
    # Smart markup data (keep as JSON)
    smart_markup_data = Column(JSON)  # Smart markup metadata
    analyst_expectations = Column(JSON)  # Analyst expectations data
    # ===========================================================================
    
    # Filing-specific specialized fields (populated based on filing_type)
    # 10-K specific
    annual_business_overview = Column(Text)
    annual_strategy_analysis = Column(Text)
    annual_risk_assessment = Column(JSON)
    auditor_opinion = Column(Text)
    three_year_financials = Column(Text)
    business_segments = Column(Text)
    risk_summary = Column(Text)
    growth_drivers = Column(Text)
    management_outlook = Column(Text)
    strategic_adjustments = Column(Text)
    market_impact_10k = Column(Text)
    
    # 10-Q specific  
    quarterly_performance = Column(JSON)
    quarterly_guidance = Column(Text)
    quarterly_vs_expectations = Column(JSON)
    expectations_comparison = Column(Text)
    cost_structure = Column(Text)
    guidance_update = Column(Text)
    growth_decline_analysis = Column(Text)
    management_tone_analysis = Column(Text)
    beat_miss_analysis = Column(Text)
    market_impact_10q = Column(Text)
    
    # 8-K specific
    event_significance = Column(String(50))  # LOW, MEDIUM, HIGH, CRITICAL
    event_impact_analysis = Column(Text)
    required_actions = Column(JSON)
    item_type = Column(String(100))
    items = Column(Text)
    event_timeline = Column(Text)
    event_nature_analysis = Column(Text)
    market_impact_analysis = Column(Text)
    key_considerations = Column(Text)
    
    # S-1 specific
    ipo_company_overview = Column(Text)
    ipo_investment_thesis = Column(Text)
    ipo_risk_factors = Column(JSON)
    ipo_valuation_analysis = Column(Text)
    ipo_details = Column(Text)
    company_overview = Column(Text)
    financial_summary = Column(Text)
    risk_categories = Column(Text)
    growth_path_analysis = Column(Text)
    competitive_moat_analysis = Column(Text)
    
    # Common fields
    fiscal_year = Column(String(10))
    fiscal_quarter = Column(String(10))
    
    # Specialized summaries for different views
    executive_summary = Column(Text)  # For detailed view
    technical_summary = Column(Text)  # For analysts
    retail_summary = Column(Text)  # For retail investors
    ai_summary = Column(Text)  # Legacy AI summary
    
    # Metadata
    word_count = Column(Integer)
    reading_time_minutes = Column(Integer)
    complexity_score = Column(Float)  # Reading level
    
    # Data quality tracking
    has_financial_statements = Column(Boolean, default=False)
    has_md_a = Column(Boolean, default=False)  # Management Discussion & Analysis
    has_risk_factors = Column(Boolean, default=False)
    data_quality_score = Column(Float)  # 0-1 score
    
    # Interaction counters
    comment_count = Column(Integer, default=0)  # Number of comments
    view_count = Column(Integer, default=0)  # Number of views
    vote_count = Column(Integer, default=0)  # Total votes
    
    # Cache control
    cache_key = Column(String(100))
    cache_expires_at = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    company = relationship("Company", back_populates="filings")
    comments = relationship("Comment", back_populates="filing", cascade="all, delete-orphan")
    user_votes = relationship("UserVote", back_populates="filing", cascade="all, delete-orphan")
    user_views = relationship("UserFilingView", back_populates="filing", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Filing(id={self.id}, ticker='{self.ticker}', type='{self.filing_type.value}', date={self.filing_date})>"
    
    @property
    def is_processed(self):
        """Check if filing has been fully processed"""
        return self.status == ProcessingStatus.COMPLETED
    
    @property
    def processing_duration(self):
        """Get processing duration in seconds"""
        if self.processing_started_at and self.processing_completed_at:
            return (self.processing_completed_at - self.processing_started_at).total_seconds()
        return None
    
    @property
    def filing_age_days(self):
        """Get age of filing in days"""
        if self.filing_date:
            return (datetime.utcnow() - self.filing_date).days
        return None
    
    @property
    def has_expectations(self):
        """Check if filing has analyst expectations (for 10-Q)"""
        return self.expected_eps is not None or self.expected_revenue is not None
    
    @property
    def beat_expectations(self):
        """Check if company beat expectations (for 10-Q)"""
        if self.filing_type == FilingType.FORM_10Q and self.has_expectations:
            eps_beat = self.eps_surprise > 0 if self.eps_surprise else None
            revenue_beat = self.revenue_surprise > 0 if self.revenue_surprise else None
            
            if eps_beat is not None and revenue_beat is not None:
                return eps_beat and revenue_beat
            elif eps_beat is not None:
                return eps_beat
            elif revenue_beat is not None:
                return revenue_beat
        return None
    
    @property
    def display_filing_type(self):
        """Get display-friendly filing type"""
        type_map = {
            FilingType.FORM_10K: "Annual Report",
            FilingType.FORM_10Q: "Quarterly Report",
            FilingType.FORM_8K: "Current Report",
            FilingType.FORM_S1: "IPO Registration",
            FilingType.FORM_S1_A: "IPO Amendment",
            FilingType.FORM_424B4: "IPO Prospectus",
            FilingType.FORM_DEF14A: "Proxy Statement",
            FilingType.FORM_20F: "Foreign Annual Report"
        }
        return type_map.get(self.filing_type, self.filing_type.value)
    
    @property
    def financial_highlights_dict(self):
        """Get financial highlights as dictionary for display"""
        if self.filing_type in [FilingType.FORM_10K, FilingType.FORM_10Q]:
            highlights = {}
            
            if self.revenue:
                highlights['revenue'] = f"${self.revenue:.1f}M"
            if self.net_income:
                highlights['net_income'] = f"${self.net_income:.1f}M"
            if self.eps:
                highlights['eps'] = f"${self.eps:.2f}"
                
            # Add expectations for 10-Q
            if self.filing_type == FilingType.FORM_10Q and self.has_expectations:
                if self.expected_eps:
                    highlights['expected_eps'] = f"${self.expected_eps:.2f}"
                if self.eps_surprise:
                    highlights['eps_surprise'] = f"{self.eps_surprise:+.2f}"
                if self.expected_revenue:
                    highlights['expected_revenue'] = f"${self.expected_revenue:.1f}M"
                if self.revenue_surprise:
                    highlights['revenue_surprise'] = f"{self.revenue_surprise:+.1%}"
                    
            return highlights
        return None
    
    @property
    def ipo_details_dict(self):
        """Get IPO details as dictionary for S-1 filings"""
        if self.filing_type in [FilingType.FORM_S1, FilingType.FORM_S1_A]:
            details = {}
            
            if self.ipo_price_range_low and self.ipo_price_range_high:
                details['price_range'] = f"${self.ipo_price_range_low}-${self.ipo_price_range_high}"
            if self.ipo_shares_offered:
                details['shares_offered'] = f"{self.ipo_shares_offered:,}"
            if self.ipo_use_of_proceeds:
                details['use_of_proceeds'] = self.ipo_use_of_proceeds
                
            return details
        return None
    
    @property
    def event_summary(self):
        """Get event summary for 8-K filings"""
        if self.filing_type == FilingType.FORM_8K:
            summary = {
                'type': self.event_type,
                'significance': self.event_significance,
                'description': self.event_description
            }
            
            if self.event_items:
                summary['items'] = self.event_items
                
            return summary
        return None
    
    def safe_json_get(self, field_name, default=None):
        """Safely get JSON field value, handling empty dicts"""
        value = getattr(self, field_name, None)
        if value is None:
            return default
        if isinstance(value, dict) and not value:  # Empty dict
            return default
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict) and not parsed:
                    return default
                return parsed
            except (json.JSONDecodeError, TypeError):
                return value
        return value
    
    def to_dict(self, include_analysis=True):
        """Convert to dictionary for API responses"""
        data = {
            'id': self.id,
            'company_id': self.company_id,
            'ticker': self.ticker,
            'filing_type': self.filing_type.value,
            'display_type': self.display_filing_type,
            'filing_date': self.filing_date.isoformat() if self.filing_date else None,
            'period_end_date': self.period_end_date.isoformat() if self.period_end_date else None,
            'filing_url': self.filing_url,
            'status': self.status.value,
            'unified_score': self.unified_score,
            'unified_feed_summary': self.unified_feed_summary,
            'sentiment_score': self.sentiment_score,
            'management_tone': self.management_tone.value if self.management_tone else None,
            'reading_time_minutes': self.reading_time_minutes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        
        # Add financial highlights for 10-K/10-Q
        if self.financial_highlights_dict:
            data['financial_highlights'] = self.financial_highlights_dict
            
        # Add IPO details for S-1
        if self.ipo_details_dict:
            data['ipo_details'] = self.ipo_details_dict
            
        # Add event summary for 8-K
        if self.event_summary:
            data['event_summary'] = self.event_summary
        
        # Include full analysis if requested
        if include_analysis and self.unified_analysis:
            data['analysis'] = {
                'unified_analysis': self.unified_analysis,
                'key_points': self.safe_json_get('key_points', []),
                'risks': self.safe_json_get('risks', []),
                'opportunities': self.safe_json_get('opportunities', []),
                'market_reaction_prediction': self.market_reaction_prediction,
                'competitive_positioning': self.competitive_positioning
            }
            
            # Add filing-specific analysis
            if self.filing_type == FilingType.FORM_10K:
                data['analysis']['annual'] = {
                    'business_overview': self.annual_business_overview,
                    'strategy_analysis': self.annual_strategy_analysis,
                    'risk_assessment': self.safe_json_get('annual_risk_assessment', [])
                }
            elif self.filing_type == FilingType.FORM_10Q:
                data['analysis']['quarterly'] = {
                    'performance': self.safe_json_get('quarterly_performance', {}),
                    'guidance': self.quarterly_guidance,
                    'vs_expectations': self.safe_json_get('quarterly_vs_expectations', {})
                }
            elif self.filing_type == FilingType.FORM_8K:
                data['analysis']['event'] = {
                    'significance': self.event_significance,
                    'impact_analysis': self.event_impact_analysis,
                    'required_actions': self.safe_json_get('required_actions', [])
                }
            elif self.filing_type in [FilingType.FORM_S1, FilingType.FORM_S1_A]:
                data['analysis']['ipo'] = {
                    'company_overview': self.ipo_company_overview,
                    'investment_thesis': self.ipo_investment_thesis,
                    'risk_factors': self.safe_json_get('ipo_risk_factors', []),
                    'valuation_analysis': self.ipo_valuation_analysis
                }
        
        return data
    
    def get_cache_key(self):
        """Generate cache key for this filing"""
        return f"filing:{self.company_id}:{self.accession_number}:{self.analysis_version}"
    
    def should_reprocess(self):
        """Check if filing should be reprocessed"""
        # Reprocess if failed and retry count is low
        if self.status == ProcessingStatus.FAILED and self.retry_count < 3:
            return True
            
        # Reprocess if old analysis version
        if self.status == ProcessingStatus.COMPLETED and self.analysis_version != "v5":
            return True
            
        return False
    
    class Meta:
        db_table = 'filings'
        indexes = [
            ('company_id', 'filing_date'),
            ('ticker', 'filing_type', 'filing_date'),
            ('status', 'created_at'),
        ]
"""
Filing schemas for API requests and responses
FIXED: All fields now properly defined as strings where appropriate
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

# 注意：不再导入 CompanyBrief，因为我们将使用字典


class FilingBase(BaseModel):
    """Base filing schema"""
    form_type: str
    filing_date: datetime
    accession_number: str
    file_url: str
    

class FilingBrief(FilingBase):
    """Brief filing info for lists"""
    id: int
    company: Dict[str, Any]  # 改为字典类型
    one_liner: Optional[str] = None
    sentiment: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    
    # Interaction stats
    vote_counts: Dict[str, int] = Field(default_factory=lambda: {"bullish": 0, "neutral": 0, "bearish": 0})
    comment_count: int = 0
    
    # For 8-K: event type
    event_type: Optional[str] = None
    
    class Config:
        from_attributes = True


class Filing10KDetail(FilingBase):
    """10-K specific detail schema"""
    id: int
    company: Dict[str, Any]  # 改为字典类型
    
    # Common fields
    ai_summary: Optional[str] = None
    fiscal_year: Optional[str] = None
    period_end_date: Optional[datetime] = None
    
    # 10-K specific - ALL STRING
    auditor_opinion: Optional[str] = None
    three_year_financials: Optional[str] = None
    business_segments: Optional[str] = None
    risk_summary: Optional[str] = None
    growth_drivers: Optional[str] = None
    management_outlook: Optional[str] = None
    strategic_adjustments: Optional[str] = None
    market_impact_10k: Optional[str] = None
    
    # Financial highlights - NOW STRING
    financial_highlights: Optional[str] = None  # ✅ CHANGED TO STRING
    
    # Interaction stats
    vote_counts: Dict[str, int] = Field(default_factory=lambda: {"bullish": 0, "neutral": 0, "bearish": 0})
    comment_count: int = 0
    user_vote: Optional[str] = None
    
    class Config:
        from_attributes = True


class Filing10QDetail(FilingBase):
    """10-Q specific detail schema"""
    id: int
    company: Dict[str, Any]  # 改为字典类型
    
    # Common fields
    ai_summary: Optional[str] = None
    fiscal_quarter: Optional[str] = None
    period_end_date: Optional[datetime] = None
    
    # 10-Q specific - ALL STRING
    expectations_comparison: Optional[str] = None
    cost_structure: Optional[str] = None
    guidance_update: Optional[str] = None
    growth_decline_analysis: Optional[str] = None
    management_tone_analysis: Optional[str] = None
    beat_miss_analysis: Optional[str] = None
    market_impact_10q: Optional[str] = None
    
    # Core metrics - NOW STRING
    core_metrics: Optional[str] = None  # ✅ CHANGED TO STRING
    
    # Interaction stats
    vote_counts: Dict[str, int] = Field(default_factory=lambda: {"bullish": 0, "neutral": 0, "bearish": 0})
    comment_count: int = 0
    user_vote: Optional[str] = None
    
    class Config:
        from_attributes = True


class Filing8KDetail(FilingBase):
    """8-K specific detail schema"""
    id: int
    company: Dict[str, Any]  # 改为字典类型
    
    # Common fields
    ai_summary: Optional[str] = None
    
    # 8-K specific - ALL STRING
    item_type: Optional[str] = None
    items: Optional[str] = None
    event_timeline: Optional[str] = None
    event_nature_analysis: Optional[str] = None
    market_impact_analysis: Optional[str] = None
    key_considerations: Optional[str] = None
    
    # Event details
    event_type: Optional[str] = None
    event_summary: Optional[str] = None
    
    # Interaction stats
    vote_counts: Dict[str, int] = Field(default_factory=lambda: {"bullish": 0, "neutral": 0, "bearish": 0})
    comment_count: int = 0
    user_vote: Optional[str] = None
    
    class Config:
        from_attributes = True


class FilingS1Detail(FilingBase):
    """S-1 specific detail schema"""
    id: int
    company: Dict[str, Any]  # 改为字典类型
    
    # Common fields
    ai_summary: Optional[str] = None
    
    # S-1 specific - ALL STRING
    ipo_details: Optional[str] = None
    company_overview: Optional[str] = None
    financial_summary: Optional[str] = None
    risk_categories: Optional[str] = None
    growth_path_analysis: Optional[str] = None
    competitive_moat_analysis: Optional[str] = None
    
    # Financial highlights - STRING
    financial_highlights: Optional[str] = None  # ✅ ADDED
    
    # Interaction stats
    vote_counts: Dict[str, int] = Field(default_factory=lambda: {"bullish": 0, "neutral": 0, "bearish": 0})
    comment_count: int = 0
    user_vote: Optional[str] = None
    
    class Config:
        from_attributes = True


class FilingDetail(FilingBase):
    """Detailed filing info with all possible fields for backward compatibility"""
    id: int
    cik: str
    company: Dict[str, Any]  # 改为字典类型
    status: str
    
    # AI-generated content
    ai_summary: Optional[str] = None
    one_liner: Optional[str] = None
    sentiment: Optional[str] = None
    sentiment_explanation: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    questions_answers: List[Dict[str, str]] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    
    # Financial metrics - NOW STRING
    financial_metrics: Optional[str] = None  # ✅ CHANGED TO STRING
    
    # Event info (for 8-K)
    event_type: Optional[str] = None
    event_details: Optional[Dict[str, Any]] = None  # Keep as Dict for backward compatibility
    
    # Differentiated display fields (existing)
    specific_data: Optional[Dict[str, Any]] = Field(default={}, description="Type-specific structured data")
    chart_data: Optional[Dict[str, Any]] = Field(default=None, description="Pre-processed chart data")
    
    # Special fields for 10-Q
    earnings_comparison: Optional[str] = Field(default=None, description="Actual vs expected earnings data")
    
    # ==================== NEW FIELDS FOR DIFFERENTIATED DISPLAY (Day 19) ====================
    
    # Common fields
    fiscal_year: Optional[str] = None
    fiscal_quarter: Optional[str] = None
    period_end_date: Optional[datetime] = None
    
    # 10-K specific fields - ALL STRING
    auditor_opinion: Optional[str] = None
    three_year_financials: Optional[str] = None
    business_segments: Optional[str] = None
    risk_summary: Optional[str] = None
    growth_drivers: Optional[str] = None
    management_outlook: Optional[str] = None
    strategic_adjustments: Optional[str] = None
    market_impact_10k: Optional[str] = None
    financial_highlights: Optional[str] = None  # ✅ ADDED FOR 10-K
    
    # 10-Q specific fields - ALL STRING
    expectations_comparison: Optional[str] = None
    cost_structure: Optional[str] = None
    guidance_update: Optional[str] = None
    growth_decline_analysis: Optional[str] = None
    management_tone_analysis: Optional[str] = None
    beat_miss_analysis: Optional[str] = None
    core_metrics: Optional[str] = None  # ✅ CHANGED TO STRING
    market_impact_10q: Optional[str] = None
    
    # 8-K specific fields - ALL STRING
    item_type: Optional[str] = None
    items: Optional[str] = None
    event_timeline: Optional[str] = None
    event_nature_analysis: Optional[str] = None
    market_impact_analysis: Optional[str] = None
    key_considerations: Optional[str] = None
    event_summary: Optional[str] = None
    
    # S-1 specific fields - ALL STRING  
    ipo_details: Optional[str] = None  # ✅ NOW ONLY ONE DEFINITION AS STRING
    company_overview: Optional[str] = None
    financial_summary: Optional[str] = None
    risk_categories: Optional[str] = None
    growth_path_analysis: Optional[str] = None
    competitive_moat_analysis: Optional[str] = None
    
    # Metadata
    processed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    # Interaction stats
    vote_counts: Dict[str, int] = Field(default_factory=lambda: {"bullish": 0, "neutral": 0, "bearish": 0})
    comment_count: int = 0
    user_vote: Optional[str] = None
    
    # View limit info
    view_limit_info: Optional[dict] = None
    
    class Config:
        from_attributes = True


class FilingList(BaseModel):
    """Paginated list of filings"""
    total: int
    skip: int
    limit: int
    data: List[FilingBrief]


class FilingCreate(BaseModel):
    """Schema for creating a filing (internal use)"""
    cik: str
    form_type: str
    filing_date: datetime
    accession_number: str
    file_url: str
    company_name: str


# Helper function to get appropriate schema
def get_filing_detail_schema(filing_type: str):
    """Get the appropriate detail schema based on filing type"""
    schema_map = {
        "10-K": Filing10KDetail,
        "10-Q": Filing10QDetail,
        "8-K": Filing8KDetail,
        "S-1": FilingS1Detail,
    }
    return schema_map.get(filing_type, FilingDetail)
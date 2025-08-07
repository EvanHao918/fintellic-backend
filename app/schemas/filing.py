"""
Filing schemas for API requests and responses
Updated to support unified analysis fields and enhanced company info
FIXED: Changed file_url to filing_url for consistency
"""
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, validator


class SmartMarkupData(BaseModel):
    """Smart markup data structure that handles both string and object sources"""
    sources: Optional[List[Union[str, Dict[str, Any]]]] = None
    insights: Optional[List[str]] = None
    positive: Optional[List[str]] = None
    negative: Optional[List[str]] = None
    numbers: Optional[List[str]] = None
    
    @validator('sources', pre=True)
    def normalize_sources(cls, v):
        """Convert object sources to strings if needed"""
        if v and isinstance(v, list):
            normalized = []
            for item in v:
                if isinstance(item, dict):
                    # Extract reference from object format
                    normalized.append(item.get('reference', str(item)))
                else:
                    normalized.append(str(item))
            return normalized
        return v


class CompanyInfo(BaseModel):
    """Company information schema - 增强版"""
    id: int
    cik: str
    ticker: str
    name: str
    
    # 基础信息（所有公司都有）
    is_sp500: bool = False
    is_nasdaq100: bool = False
    is_public: bool = True
    has_s1_filing: bool = False
    
    # 扩展信息（成熟公司可能有）
    legal_name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    headquarters: Optional[str] = None
    country: Optional[str] = "United States"
    founded_year: Optional[int] = None
    employees: Optional[int] = None
    employee_size: Optional[str] = None
    market_cap: Optional[float] = None
    exchange: Optional[str] = None
    indices: List[str] = Field(default_factory=list)
    company_type: Optional[str] = None
    website: Optional[str] = None
    fiscal_year_end: Optional[str] = None
    state: Optional[str] = None
    ipo_date: Optional[str] = None
    
    class Config:
        from_attributes = True


class FilingBase(BaseModel):
    """Base filing schema"""
    form_type: str
    filing_date: datetime
    accession_number: str
    filing_url: str  # 👈 修改：从 file_url 改为 filing_url
    

class FilingBrief(FilingBase):
    """Brief filing info for lists"""
    id: int
    company: CompanyInfo  # 使用增强的CompanyInfo
    one_liner: Optional[str] = None
    sentiment: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    
    # Interaction stats
    vote_counts: Dict[str, int] = Field(default_factory=lambda: {"bullish": 0, "neutral": 0, "bearish": 0})
    comment_count: int = 0
    view_count: int = 0
    
    # For 8-K: event type
    event_type: Optional[str] = None
    
    # New unified fields
    has_unified_analysis: bool = False
    
    class Config:
        from_attributes = True


class FilingDetail(FilingBase):
    """Detailed filing info with unified analysis support and enhanced company info"""
    id: int
    cik: str
    company: CompanyInfo  # 使用增强的CompanyInfo
    status: str
    
    # ==================== UNIFIED ANALYSIS FIELDS ====================
    # Core unified content
    unified_analysis: Optional[str] = Field(None, description="Unified 800-1200 word analysis")
    unified_feed_summary: Optional[str] = Field(None, description="One-line feed summary")
    analysis_version: Optional[str] = Field(None, description="v1=legacy, v2=unified")
    smart_markup_data: Optional[Union[Dict[str, Any], SmartMarkupData]] = Field(None, description="Smart markup metadata")
    analyst_expectations: Optional[Dict[str, Any]] = Field(None, description="Analyst expectations data")
    
    # ==================== LEGACY FIELDS (for backward compatibility) ====================
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
    
    # Financial metrics - FIXED: All are Optional[str]
    financial_metrics: Optional[str] = None
    financial_highlights: Optional[str] = None
    core_metrics: Optional[str] = None
    
    # Event info (for 8-K)
    event_type: Optional[str] = None
    event_details: Optional[Dict[str, Any]] = None
    
    # Differentiated display fields
    specific_data: Optional[Dict[str, Any]] = Field(default={}, description="Type-specific structured data")
    chart_data: Optional[Dict[str, Any]] = Field(default=None, description="Pre-processed chart data")
    
    # Special fields for 10-Q
    earnings_comparison: Optional[str] = Field(default=None, description="Actual vs expected earnings data")
    
    # Common fields
    fiscal_year: Optional[str] = None
    fiscal_quarter: Optional[str] = None
    period_end_date: Optional[datetime] = None
    
    # 10-K specific fields
    auditor_opinion: Optional[str] = None
    three_year_financials: Optional[str] = None
    business_segments: Optional[str] = None
    risk_summary: Optional[str] = None
    growth_drivers: Optional[str] = None
    management_outlook: Optional[str] = None
    strategic_adjustments: Optional[str] = None
    market_impact_10k: Optional[str] = None
    
    # 10-Q specific fields
    expectations_comparison: Optional[str] = None
    cost_structure: Optional[str] = None
    guidance_update: Optional[str] = None
    growth_decline_analysis: Optional[str] = None
    management_tone_analysis: Optional[str] = None
    beat_miss_analysis: Optional[str] = None
    market_impact_10q: Optional[str] = None
    
    # 8-K specific fields
    item_type: Optional[str] = None
    items: Optional[str] = None
    event_timeline: Optional[str] = None
    event_nature_analysis: Optional[str] = None
    market_impact_analysis: Optional[str] = None
    key_considerations: Optional[str] = None
    event_summary: Optional[str] = None
    
    # S-1 specific fields
    ipo_details: Optional[str] = None
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
    view_count: int = 0
    
    # View limit info
    view_limit_info: Optional[dict] = None
    
    @validator('smart_markup_data', pre=True)
    def normalize_smart_markup(cls, v):
        """Normalize smart_markup_data to handle both formats"""
        if v and isinstance(v, dict):
            # Check if sources field needs normalization
            if 'sources' in v and isinstance(v['sources'], list):
                normalized_sources = []
                for item in v['sources']:
                    if isinstance(item, dict):
                        # Convert object to string (extract reference)
                        normalized_sources.append(item.get('reference', str(item)))
                    else:
                        normalized_sources.append(str(item))
                v['sources'] = normalized_sources
        return v
    
    @validator('financial_metrics', 'financial_highlights', 'core_metrics', pre=True)
    def normalize_financial_fields(cls, v):
        """Convert JSON/dict to string if needed"""
        if v is None:
            return None
        if isinstance(v, dict):
            if not v:  # Empty dict
                return None
            import json
            return json.dumps(v)
        if isinstance(v, str):
            return v if v else None
        return str(v) if v else None
    
    class Config:
        from_attributes = True
        
    @property
    def display_summary(self) -> Optional[str]:
        """Get display summary - prefer unified over legacy"""
        if self.analysis_version == "v2" and self.unified_analysis:
            return self.unified_analysis
        return self.ai_summary
    
    @property
    def display_one_liner(self) -> Optional[str]:
        """Get one-liner - prefer unified feed summary"""
        if self.unified_feed_summary:
            return self.unified_feed_summary
        return self.one_liner


# 保留其他Detail类不变...
class Filing10KDetail(FilingBase):
    """10-K specific detail schema with unified support"""
    id: int
    company: CompanyInfo  # 使用增强的CompanyInfo
    
    # Unified fields
    unified_analysis: Optional[str] = None
    unified_feed_summary: Optional[str] = None
    smart_markup_data: Optional[Union[Dict[str, Any], SmartMarkupData]] = None
    
    # Common fields
    ai_summary: Optional[str] = None
    fiscal_year: Optional[str] = None
    period_end_date: Optional[datetime] = None
    
    # 10-K specific - FIXED: All are Optional[str]
    auditor_opinion: Optional[str] = None
    three_year_financials: Optional[str] = None
    business_segments: Optional[str] = None
    risk_summary: Optional[str] = None
    growth_drivers: Optional[str] = None
    management_outlook: Optional[str] = None
    strategic_adjustments: Optional[str] = None
    market_impact_10k: Optional[str] = None
    financial_highlights: Optional[str] = None
    
    # Interaction stats
    vote_counts: Dict[str, int] = Field(default_factory=lambda: {"bullish": 0, "neutral": 0, "bearish": 0})
    comment_count: int = 0
    user_vote: Optional[str] = None
    view_count: int = 0
    
    @validator('smart_markup_data', pre=True)
    def normalize_smart_markup(cls, v):
        """Normalize smart_markup_data to handle both formats"""
        if v and isinstance(v, dict):
            if 'sources' in v and isinstance(v['sources'], list):
                normalized_sources = []
                for item in v['sources']:
                    if isinstance(item, dict):
                        normalized_sources.append(item.get('reference', str(item)))
                    else:
                        normalized_sources.append(str(item))
                v['sources'] = normalized_sources
        return v
    
    @validator('financial_highlights', pre=True)
    def normalize_financial_highlights(cls, v):
        """Convert JSON/dict to string if needed"""
        if v is None:
            return None
        if isinstance(v, dict):
            if not v:  # Empty dict
                return None
            import json
            return json.dumps(v)
        if isinstance(v, str):
            return v if v else None
        return str(v) if v else None
    
    class Config:
        from_attributes = True


class Filing10QDetail(FilingBase):
    """10-Q specific detail schema with unified support"""
    id: int
    company: CompanyInfo  # 使用增强的CompanyInfo
    
    # Unified fields
    unified_analysis: Optional[str] = None
    unified_feed_summary: Optional[str] = None
    smart_markup_data: Optional[Union[Dict[str, Any], SmartMarkupData]] = None
    analyst_expectations: Optional[Dict[str, Any]] = None
    
    # Common fields
    ai_summary: Optional[str] = None
    fiscal_quarter: Optional[str] = None
    period_end_date: Optional[datetime] = None
    
    # 10-Q specific - FIXED: All are Optional[str]
    expectations_comparison: Optional[str] = None
    cost_structure: Optional[str] = None
    guidance_update: Optional[str] = None
    growth_decline_analysis: Optional[str] = None
    management_tone_analysis: Optional[str] = None
    beat_miss_analysis: Optional[str] = None
    market_impact_10q: Optional[str] = None
    core_metrics: Optional[str] = None
    financial_highlights: Optional[str] = None
    
    # Interaction stats
    vote_counts: Dict[str, int] = Field(default_factory=lambda: {"bullish": 0, "neutral": 0, "bearish": 0})
    comment_count: int = 0
    user_vote: Optional[str] = None
    view_count: int = 0
    
    @validator('smart_markup_data', pre=True)
    def normalize_smart_markup(cls, v):
        """Normalize smart_markup_data to handle both formats"""
        if v and isinstance(v, dict):
            if 'sources' in v and isinstance(v['sources'], list):
                normalized_sources = []
                for item in v['sources']:
                    if isinstance(item, dict):
                        normalized_sources.append(item.get('reference', str(item)))
                    else:
                        normalized_sources.append(str(item))
                v['sources'] = normalized_sources
        return v
    
    @validator('core_metrics', 'financial_highlights', pre=True)
    def normalize_financial_fields(cls, v):
        """Convert JSON/dict to string if needed"""
        if v is None:
            return None
        if isinstance(v, dict):
            if not v:  # Empty dict
                return None
            import json
            return json.dumps(v)
        if isinstance(v, str):
            return v if v else None
        return str(v) if v else None
    
    class Config:
        from_attributes = True


class Filing8KDetail(FilingBase):
    """8-K specific detail schema with unified support"""
    id: int
    company: CompanyInfo  # 使用增强的CompanyInfo
    
    # Unified fields
    unified_analysis: Optional[str] = None
    unified_feed_summary: Optional[str] = None
    smart_markup_data: Optional[Union[Dict[str, Any], SmartMarkupData]] = None
    
    # Common fields
    ai_summary: Optional[str] = None
    
    # 8-K specific
    item_type: Optional[str] = None
    items: Optional[str] = None
    event_timeline: Optional[str] = None
    event_nature_analysis: Optional[str] = None
    market_impact_analysis: Optional[str] = None
    key_considerations: Optional[str] = None
    event_type: Optional[str] = None
    event_summary: Optional[str] = None
    
    # Interaction stats
    vote_counts: Dict[str, int] = Field(default_factory=lambda: {"bullish": 0, "neutral": 0, "bearish": 0})
    comment_count: int = 0
    user_vote: Optional[str] = None
    view_count: int = 0
    
    @validator('smart_markup_data', pre=True)
    def normalize_smart_markup(cls, v):
        """Normalize smart_markup_data to handle both formats"""
        if v and isinstance(v, dict):
            if 'sources' in v and isinstance(v['sources'], list):
                normalized_sources = []
                for item in v['sources']:
                    if isinstance(item, dict):
                        normalized_sources.append(item.get('reference', str(item)))
                    else:
                        normalized_sources.append(str(item))
                v['sources'] = normalized_sources
        return v
    
    class Config:
        from_attributes = True


class FilingS1Detail(FilingBase):
    """S-1 specific detail schema with unified support"""
    id: int
    company: CompanyInfo  # 使用增强的CompanyInfo
    
    # Unified fields
    unified_analysis: Optional[str] = None
    unified_feed_summary: Optional[str] = None
    smart_markup_data: Optional[Union[Dict[str, Any], SmartMarkupData]] = None
    
    # Common fields
    ai_summary: Optional[str] = None
    
    # S-1 specific - FIXED: All are Optional[str]
    ipo_details: Optional[str] = None
    company_overview: Optional[str] = None
    financial_summary: Optional[str] = None
    risk_categories: Optional[str] = None
    growth_path_analysis: Optional[str] = None
    competitive_moat_analysis: Optional[str] = None
    financial_highlights: Optional[str] = None
    
    # Interaction stats
    vote_counts: Dict[str, int] = Field(default_factory=lambda: {"bullish": 0, "neutral": 0, "bearish": 0})
    comment_count: int = 0
    user_vote: Optional[str] = None
    view_count: int = 0
    
    @validator('smart_markup_data', pre=True)
    def normalize_smart_markup(cls, v):
        """Normalize smart_markup_data to handle both formats"""
        if v and isinstance(v, dict):
            if 'sources' in v and isinstance(v['sources'], list):
                normalized_sources = []
                for item in v['sources']:
                    if isinstance(item, dict):
                        normalized_sources.append(item.get('reference', str(item)))
                    else:
                        normalized_sources.append(str(item))
                v['sources'] = normalized_sources
        return v
    
    @validator('financial_highlights', pre=True)
    def normalize_financial_highlights(cls, v):
        """Convert JSON/dict to string if needed"""
        if v is None:
            return None
        if isinstance(v, dict):
            if not v:  # Empty dict
                return None
            import json
            return json.dumps(v)
        if isinstance(v, str):
            return v if v else None
        return str(v) if v else None
    
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
    filing_url: str  # 👈 修改：从 file_url 改为 filing_url
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
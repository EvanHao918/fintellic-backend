"""
Filing schemas for API requests and responses
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.company import CompanyBrief


class FilingBase(BaseModel):
    """Base filing schema"""
    form_type: str
    filing_date: datetime
    accession_number: str
    file_url: str
    
    
class FilingBrief(FilingBase):
    """Brief filing info for lists"""
    id: int
    company: CompanyBrief
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


class FilingDetail(FilingBase):
    """Detailed filing info"""
    id: int
    cik: str
    company: CompanyBrief
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
    
    # Financial metrics (for 10-K and 10-Q)
    financial_metrics: Optional[Dict[str, Any]] = None
    
    # Event info (for 8-K)
    event_type: Optional[str] = None
    event_details: Optional[Dict[str, Any]] = None
    
    # IPO info (for S-1)
    ipo_details: Optional[Dict[str, Any]] = None
    
    # Differentiated display fields (new)
    specific_data: Optional[Dict[str, Any]] = Field(default={}, description="Type-specific structured data")
    chart_data: Optional[Dict[str, Any]] = Field(default=None, description="Pre-processed chart data")
    
    # Special fields for 10-Q
    earnings_comparison: Optional[Dict[str, Any]] = Field(default=None, description="Actual vs expected earnings data")
    
    # Metadata
    processed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    # Add this new field
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
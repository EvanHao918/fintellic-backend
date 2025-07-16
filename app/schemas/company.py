# app/schemas/company.py
"""
Company schemas for API requests and responses
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class CompanyBase(BaseModel):
    """Base company schema"""
    ticker: str
    name: str
    cik: str
    

class CompanyBrief(CompanyBase):
    """Brief company info for embedding in other schemas"""
    id: int
    sector: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class CompanyDetail(CompanyBase):
    """Detailed company information"""
    id: int
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    employees: Optional[int] = None
    description: Optional[str] = None
    website: Optional[str] = None
    
    # New fields for Day 8
    sic: Optional[str] = None
    sic_description: Optional[str] = None
    business_address: Optional[str] = None
    mailing_address: Optional[str] = None
    business_phone: Optional[str] = None
    incorporated_location: Optional[str] = None
    in_sp500: bool = True
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    # Filing statistics
    filing_stats: Dict[str, int] = {}
    recent_filings: List[Dict[str, Any]] = []
    
    # Additional computed fields
    total_filings: int = 0
    is_watched: bool = False  # Will be set based on current user
    
    model_config = ConfigDict(from_attributes=True)


class CompanyList(BaseModel):
    """Paginated list of companies"""
    total: int
    skip: int
    limit: int
    data: List[CompanyBrief]


class CompanySearch(BaseModel):
    """Company search results"""
    query: str
    results: List[CompanyBrief]
    total: int
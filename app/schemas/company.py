# app/schemas/company.py
"""
Company schemas for API requests and responses
UPDATED: Added FMP data fields for the FMP API optimization project
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel


class CompanyBase(BaseModel):
    """Base company schema"""
    ticker: str
    name: str
    cik: str
    

class CompanyBrief(CompanyBase):
    """Brief company info for embedding in other schemas"""
    id: int
    sector: Optional[str] = None
    
    class Config:
        from_attributes = True


class CompanyDetail(CompanyBase):
    """
    Detailed company information
    UPDATED: Enhanced with FMP data fields for optimization project
    """
    id: int
    sector: Optional[str] = None
    industry: Optional[str] = None
    
    # UPDATED: Enhanced FMP data fields (core optimization)
    market_cap: Optional[float] = None
    market_cap_formatted: Optional[str] = None  # NEW: Formatted display value
    pe_ratio: Optional[float] = None            # NEW: PE ratio from FMP
    pe_ratio_formatted: Optional[str] = None    # NEW: Formatted PE ratio
    website: Optional[str] = None               # UPDATED: Now properly included
    
    employees: Optional[int] = None
    description: Optional[str] = None
    headquarters: Optional[str] = None          # NEW: Company headquarters
    country: Optional[str] = None               # NEW: Country information
    
    # Existing fields
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
    
    class Config:
        from_attributes = True


class CompanyProfile(BaseModel):
    """
    Company profile schema for /companies/{ticker}/profile endpoint
    UPDATED: Optimized for FMP API optimization project
    """
    # Core identifiers
    ticker: str
    name: str
    cik: str
    
    # Classification
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    
    # CORE OPTIMIZATION: FMP data now served from database
    market_cap: Optional[float] = None
    market_cap_formatted: Optional[str] = None
    pe_ratio: Optional[float] = None
    pe_ratio_formatted: Optional[str] = None
    website: Optional[str] = None
    
    # Location and basic info
    headquarters: Optional[str] = None
    country: Optional[str] = None
    employees: Optional[int] = None
    founded_year: Optional[int] = None
    
    # Market classification
    is_sp500: bool = False
    is_nasdaq100: bool = False
    is_public: bool = True
    has_s1_filing: bool = False
    
    # Additional details
    fiscal_year_end: Optional[str] = None
    state: Optional[str] = None
    
    # Optional real-time market data (only if specifically requested)
    price: Optional[float] = None
    beta: Optional[float] = None
    volume_avg: Optional[int] = None
    
    # Optional enhanced data
    description: Optional[str] = None
    ceo: Optional[str] = None
    key_metrics: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


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


class CompanyFMPData(BaseModel):
    """
    FMP API data structure for optional enhanced data
    UPDATED: Used as fallback when database data is incomplete
    """
    # Market data
    market_cap: Optional[float] = None
    market_cap_formatted: Optional[str] = None
    pe_ratio: Optional[float] = None
    price: Optional[float] = None
    beta: Optional[float] = None
    volume_avg: Optional[int] = None
    
    # Company info
    sector: Optional[str] = None
    industry: Optional[str] = None
    headquarters: Optional[str] = None
    country: Optional[str] = None
    employees: Optional[int] = None
    website: Optional[str] = None
    description: Optional[str] = None
    ceo: Optional[str] = None
    
    # Metadata
    fetch_timestamp: Optional[str] = None
    data_source: Optional[str] = None
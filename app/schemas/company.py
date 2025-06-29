"""
Company schemas for API requests and responses
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class CompanyBase(BaseModel):
    """Base company schema"""
    ticker: str
    name: str
    cik: str
    

class CompanyBrief(CompanyBase):
    """Brief company info for embedding in other schemas"""
    sector: Optional[str] = None
    
    class Config:
        from_attributes = True


class CompanyDetail(CompanyBase):
    """Detailed company information"""
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    employees: Optional[int] = None
    description: Optional[str] = None
    website: Optional[str] = None
    
    # Additional computed fields
    total_filings: int = 0
    is_watched: bool = False  # Will be set based on current user
    
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
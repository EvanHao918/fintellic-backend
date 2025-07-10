# app/schemas/watchlist.py
"""
Watchlist schemas for request/response validation
"""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class WatchedCompany(BaseModel):
    """Schema for a watched company with details"""
    ticker: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    is_sp500: bool
    is_nasdaq100: bool
    indices: List[str]
    added_at: str
    last_filing: Optional[dict] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class WatchlistResponse(BaseModel):
    """Response for watchlist operations"""
    watchlist: List[WatchedCompany]
    total_count: int


class WatchlistAddResponse(BaseModel):
    """Response for adding to watchlist"""
    message: str
    ticker: str
    name: str
    watchlist_count: int


class WatchlistRemoveResponse(BaseModel):
    """Response for removing from watchlist"""
    message: str
    ticker: str
    watchlist_count: int


class WatchlistStatusResponse(BaseModel):
    """Response for checking watchlist status"""
    ticker: str
    is_watchlisted: bool
    watchlist_count: int


class WatchlistCountResponse(BaseModel):
    """Response for watchlist count"""
    count: int
    limit: Optional[int] = Field(None, description="Always None since no limits")
    is_pro: bool  # 保留字段以兼容前端


class CompanySearchResult(BaseModel):
    """Search result for watchable companies"""
    ticker: str
    name: str
    sector: Optional[str] = None
    is_sp500: bool
    is_nasdaq100: bool
    indices: List[str]
    is_watchlisted: bool
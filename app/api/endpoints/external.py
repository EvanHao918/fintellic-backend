"""
External API endpoints for third-party developers
Provides read-only access to filing data via API Key authentication
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from app.api import deps
from app.core.database import get_db
from app.models.filing import Filing, ProcessingStatus
from app.models.company import Company
from app.models import UserVote

router = APIRouter()


def get_vote_counts(db: Session, filing_id: int) -> Dict[str, int]:
    """Get vote counts for a filing"""
    votes = db.query(UserVote).filter(UserVote.filing_id == filing_id).all()
    counts = {"bullish": 0, "neutral": 0, "bearish": 0}
    for vote in votes:
        if vote.vote_type in counts:
            counts[vote.vote_type] += 1
    return counts


def format_company_info(company: Company) -> dict:
    """Format company information for external API response"""
    return {
        "id": company.id,
        "ticker": company.ticker,
        "name": company.name,
        "cik": company.cik,
        "sector": getattr(company, 'sector', company.sic_description),
        "industry": getattr(company, 'industry', None),
        "is_sp500": company.is_sp500,
        "is_nasdaq100": company.is_nasdaq100,
        "market_cap": getattr(company, 'market_cap', None),
        "headquarters": getattr(company, 'headquarters', None)
    }


def format_filing_brief(filing: Filing, db: Session) -> dict:
    """Format filing for list response"""
    vote_counts = get_vote_counts(db, filing.id)
    
    return {
        "id": filing.id,
        "form_type": filing.filing_type.value,
        "filing_date": filing.filing_date.isoformat() if filing.filing_date else None,
        "detected_at": filing.detected_at.isoformat() if filing.detected_at else None,
        "accession_number": filing.accession_number,
        "filing_url": filing.primary_document_url or filing.filing_url or "",
        "company": format_company_info(filing.company),
        "summary": filing.unified_feed_summary,
        "event_type": filing.event_type,
        "sentiment": filing.management_tone.value if filing.management_tone else None,
        "tags": filing.key_tags if filing.key_tags else [],
        "vote_counts": vote_counts,
        "has_analysis": filing.analysis_version == "v2"
    }


def format_filing_detail(filing: Filing, db: Session) -> dict:
    """Format filing for detail response"""
    vote_counts = get_vote_counts(db, filing.id)
    
    base_data = {
        "id": filing.id,
        "form_type": filing.filing_type.value,
        "filing_date": filing.filing_date.isoformat() if filing.filing_date else None,
        "detected_at": filing.detected_at.isoformat() if filing.detected_at else None,
        "accession_number": filing.accession_number,
        "filing_url": filing.primary_document_url or filing.filing_url or "",
        "company": format_company_info(filing.company),
        
        # Analysis content
        "summary": filing.unified_feed_summary,
        "analysis": filing.unified_analysis,
        "analysis_version": filing.analysis_version,
        
        # Metadata
        "event_type": filing.event_type,
        "sentiment": filing.management_tone.value if filing.management_tone else None,
        "tags": filing.key_tags if filing.key_tags else [],
        "vote_counts": vote_counts,
        
        # Timestamps
        "processed_at": filing.processing_completed_at.isoformat() if filing.processing_completed_at else None,
        "created_at": filing.created_at.isoformat() if filing.created_at else None
    }
    
    # Add type-specific fields
    filing_type = filing.filing_type.value
    
    if filing_type == "10-Q":
        base_data["quarterly_data"] = {
            "fiscal_year": getattr(filing, 'fiscal_year', None),
            "fiscal_quarter": getattr(filing, 'fiscal_quarter', None),
            "period_end_date": filing.period_end_date.isoformat() if filing.period_end_date else None,
            "expectations_comparison": getattr(filing, 'expectations_comparison', None),
            "guidance_update": getattr(filing, 'guidance_update', None),
            "beat_miss_analysis": getattr(filing, 'beat_miss_analysis', None)
        }
    
    elif filing_type == "10-K":
        base_data["annual_data"] = {
            "fiscal_year": getattr(filing, 'fiscal_year', None),
            "period_end_date": filing.period_end_date.isoformat() if filing.period_end_date else None,
            "auditor_opinion": getattr(filing, 'auditor_opinion', None),
            "risk_summary": getattr(filing, 'risk_summary', None),
            "management_outlook": getattr(filing, 'management_outlook', None)
        }
    
    elif filing_type == "8-K":
        base_data["event_data"] = {
            "item_type": getattr(filing, 'item_type', None),
            "items": getattr(filing, 'items', None),
            "event_nature_analysis": getattr(filing, 'event_nature_analysis', None),
            "market_impact_analysis": getattr(filing, 'market_impact_analysis', None)
        }
    
    elif filing_type == "S-1":
        base_data["ipo_data"] = {
            "ipo_details": getattr(filing, 'ipo_details', None),
            "company_overview": getattr(filing, 'company_overview', None),
            "risk_categories": getattr(filing, 'risk_categories', None)
        }
    
    return base_data


@router.get("/filings")
async def get_filings_external(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=50, description="Maximum number of records to return"),
    form_type: Optional[str] = Query(None, description="Filter by form type: 10-K, 10-Q, 8-K, S-1"),
    ticker: Optional[str] = Query(None, description="Filter by company ticker"),
    db: Session = Depends(get_db),
    api_key: str = Depends(deps.verify_external_api_key)
):
    """
    Get list of SEC filings with AI analysis
    
    Requires X-API-Key header for authentication.
    Rate limited to 100 calls per day.
    
    Returns:
        List of filings with company info, summary, and metadata
    """
    # Build query
    query = db.query(Filing).options(joinedload(Filing.company))
    
    # Apply filters
    if form_type and form_type.upper() in ['10-K', '10-Q', '8-K', 'S-1']:
        query = query.filter(Filing.form_type == form_type.upper())
    
    if ticker:
        query = query.join(Company).filter(Company.ticker == ticker.upper())
    
    # Only show completed filings
    query = query.filter(Filing.status == ProcessingStatus.COMPLETED)
    
    # Get total count
    total = query.count()
    
    # Order by detection time (newest first)
    query = query.order_by(
        desc(Filing.detected_at).nulls_last(),
        desc(Filing.filing_date)
    )
    
    # Paginate
    filings = query.offset(skip).limit(limit).all()
    
    # Format response
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [format_filing_brief(f, db) for f in filings]
    }


@router.get("/filings/{filing_id}")
async def get_filing_detail_external(
    filing_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(deps.verify_external_api_key)
):
    """
    Get detailed filing information including full AI analysis
    
    Requires X-API-Key header for authentication.
    Rate limited to 100 calls per day.
    
    Returns:
        Complete filing details with analysis, company info, and type-specific data
    """
    # Get filing with company
    filing = db.query(Filing).options(
        joinedload(Filing.company)
    ).filter(Filing.id == filing_id).first()
    
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    if filing.status != ProcessingStatus.COMPLETED:
        raise HTTPException(status_code=404, detail="Filing analysis not yet available")
    
    return format_filing_detail(filing, db)


@router.get("/companies")
async def get_companies_external(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    index: Optional[str] = Query(None, description="Filter by index: sp500, nasdaq100"),
    db: Session = Depends(get_db),
    api_key: str = Depends(deps.verify_external_api_key)
):
    """
    Get list of tracked companies
    
    Requires X-API-Key header for authentication.
    """
    query = db.query(Company)
    
    # Filter by index
    if index:
        if index.lower() == "sp500":
            query = query.filter(Company.is_sp500 == True)
        elif index.lower() == "nasdaq100":
            query = query.filter(Company.is_nasdaq100 == True)
    
    total = query.count()
    companies = query.offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [format_company_info(c) for c in companies]
    }


@router.get("/status")
async def get_api_status(
    api_key: str = Depends(deps.verify_external_api_key)
):
    """
    Check API status and rate limit info
    
    Returns:
        API status and remaining rate limit
    """
    from app.core.cache import cache
    from app.core.config import settings
    
    # Get current usage
    today = datetime.utcnow().strftime("%Y-%m-%d")
    rate_limit_key = f"{deps.EXTERNAL_API_RATE_LIMIT_PREFIX}{api_key}:{today}"
    current_count = cache.get(rate_limit_key) or 0
    
    return {
        "status": "operational",
        "api_version": "v1",
        "rate_limit": {
            "daily_limit": settings.EXTERNAL_API_DAILY_LIMIT,
            "calls_used": current_count,
            "calls_remaining": max(0, settings.EXTERNAL_API_DAILY_LIMIT - current_count),
            "resets_at": "midnight UTC"
        }
    }
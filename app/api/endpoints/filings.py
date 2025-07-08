# app/api/endpoints/filings.py
"""
Filing-related API endpoints with caching support
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from app.api import deps
from app.models.filing import Filing, ProcessingStatus
from app.models.company import Company
from app.schemas.filing import FilingBrief, FilingDetail, FilingList
from app.schemas.company import CompanyBrief
from app.core.cache import cache, FilingCache, StatsCache, CACHE_TTL

router = APIRouter()


@router.get("/", response_model=FilingList)
async def get_filings(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    form_type: Optional[str] = Query(None, description="Filter by form type (10-K, 10-Q, 8-K, S-1)"),
    ticker: Optional[str] = Query(None, description="Filter by company ticker"),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Get list of filings with optional filters
    Results are cached for 5 minutes
    """
    # Generate cache key
    cache_key = FilingCache.get_filing_list_key(skip, limit, form_type, ticker)
    
    # Try cache first
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result
    
    # Build query
    query = db.query(Filing).options(joinedload(Filing.company))
    
    # Apply filters
    if form_type:
        query = query.filter(Filing.filing_type == form_type)
    if ticker:
        query = query.join(Company).filter(Company.ticker == ticker)
    
    # Only show completed filings
    query = query.filter(Filing.status == ProcessingStatus.COMPLETED)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    filings = query.order_by(desc(Filing.filing_date)).offset(skip).limit(limit).all()
    
    # Convert to response format
    filing_responses = []
    for filing in filings:
        # Get stats from cache
        view_count = StatsCache.get_view_count(str(filing.id))
        
        # Get vote counts from database
        vote_counts = {
            "bullish": filing.bullish_votes or 0,
            "neutral": filing.neutral_votes or 0,
            "bearish": filing.bearish_votes or 0
        }
        
        filing_brief = FilingBrief(
            id=filing.id,
            form_type=filing.filing_type.value,
            filing_date=filing.filing_date,
            accession_number=filing.accession_number,
            file_url=filing.primary_doc_url or "",
            company=CompanyBrief(
                id=filing.company.id,
                name=filing.company.name,
                ticker=filing.company.ticker,
                cik=filing.company.cik
            ),
            one_liner=filing.ai_summary[:100] + "..." if filing.ai_summary else None,
            sentiment=filing.management_tone.value if filing.management_tone else None,
            tags=filing.key_tags or [],
            vote_counts=vote_counts,
            comment_count=filing.comment_count or 0
        )
        filing_responses.append(filing_brief)
    
    result = FilingList(
        total=total,
        skip=skip,
        limit=limit,
        data=filing_responses
    )
    
    # Cache the result
    cache.set(cache_key, result.dict(), ttl=CACHE_TTL["filing_list"])
    
    return result


@router.get("/{filing_id}", response_model=FilingDetail)
async def get_filing(
    filing_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Get specific filing by ID
    Results are cached for 1 hour
    """
    # Generate cache key
    cache_key = FilingCache.get_filing_detail_key(str(filing_id))
    
    # Try cache first
    cached_result = cache.get(cache_key)
    if cached_result:
        # Still increment view count even for cached results
        StatsCache.increment_view_count(str(filing_id))
        return cached_result
    
    # Get from database
    filing = db.query(Filing).options(joinedload(Filing.company)).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    # Increment view count
    view_count = StatsCache.increment_view_count(str(filing_id))
    
    # Get vote counts from database
    vote_counts = {
        "bullish": filing.bullish_votes or 0,
        "neutral": filing.neutral_votes or 0,
        "bearish": filing.bearish_votes or 0
    }
    
    # Prepare response
    filing_detail = FilingDetail(
        id=filing.id,
        form_type=filing.filing_type.value,
        filing_date=filing.filing_date,
        accession_number=filing.accession_number,
        file_url=filing.primary_doc_url or "",
        cik=filing.company.cik,
        company=CompanyBrief(
            id=filing.company.id,
            name=filing.company.name,
            ticker=filing.company.ticker,
            cik=filing.company.cik
        ),
        status=filing.status.value,
        ai_summary=filing.ai_summary,
        one_liner=filing.ai_summary[:100] + "..." if filing.ai_summary else None,
        sentiment=filing.management_tone.value if filing.management_tone else None,
        sentiment_explanation=filing.tone_explanation,
        key_points=[],  # Extract from ai_summary if needed
        risks=[],  # To be extracted from filing
        opportunities=[],  # To be extracted from filing
        questions_answers=filing.key_questions or [],
        tags=filing.key_tags or [],
        financial_metrics=filing.financial_highlights,
        processed_at=filing.processing_completed_at,
        created_at=filing.created_at,
        updated_at=filing.updated_at
    )
    
    # Cache the result
    cache.set(cache_key, filing_detail.dict(), ttl=CACHE_TTL["filing_detail"])
    
    return filing_detail


@router.get("/popular/{period}")
async def get_popular_filings(
    period: str = "day",  # day, week, month
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Get popular filings based on view count
    Results are cached for 10 minutes
    """
    # Validate period
    if period not in ["day", "week", "month"]:
        raise HTTPException(status_code=400, detail="Invalid period. Use: day, week, month")
    
    # Generate cache key
    cache_key = StatsCache.get_popular_filings_key(period)
    
    # Try cache first
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result
    
    # Calculate date range
    from datetime import timedelta
    now = datetime.utcnow()
    
    if period == "day":
        start_date = now - timedelta(days=1)
    elif period == "week":
        start_date = now - timedelta(days=7)
    else:  # month
        start_date = now - timedelta(days=30)
    
    # Get filings from date range
    filings = db.query(Filing).options(joinedload(Filing.company)).filter(
        Filing.created_at >= start_date,
        Filing.status == ProcessingStatus.COMPLETED
    ).order_by(desc(Filing.created_at)).limit(100).all()
    
    # Sort by view count
    filing_views = []
    for filing in filings:
        view_count = StatsCache.get_view_count(str(filing.id))
        if view_count > 0:
            filing_views.append({
                "filing": filing,
                "view_count": view_count
            })
    
    # Sort and limit
    filing_views.sort(key=lambda x: x["view_count"], reverse=True)
    filing_views = filing_views[:limit]
    
    # Format response
    result = []
    for item in filing_views:
        filing = item["filing"]
        
        # Get vote counts from database
        vote_counts = {
            "bullish": filing.bullish_votes or 0,
            "neutral": filing.neutral_votes or 0,
            "bearish": filing.bearish_votes or 0
        }
        
        result.append({
            "id": filing.id,
            "company_name": filing.company.name,
            "company_ticker": filing.company.ticker,
            "form_type": filing.filing_type.value,
            "filing_date": filing.filing_date.isoformat(),
            "ai_summary": filing.ai_summary[:200] + "..." if filing.ai_summary else None,
            "view_count": item["view_count"],
            "votes": vote_counts,
            "created_at": filing.created_at.isoformat()
        })
    
    # Cache the result
    cache.set(cache_key, result, ttl=CACHE_TTL["popular_filings"])
    
    return result


# 删除了旧的投票端点，现在使用 interactions.py 中的投票端点
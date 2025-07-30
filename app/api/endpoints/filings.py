# app/api/endpoints/filings.py
"""
Filing-related API endpoints with caching support and view tracking
FIXED: All financial_metrics and core_metrics now expect text narratives, not JSON
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from app.api import deps
from app.models.filing import Filing, ProcessingStatus
from app.models.company import Company
from app.models import UserVote
from app.services.view_tracking import ViewTrackingService
from app.schemas.filing import FilingBrief, FilingDetail, FilingList
from app.core.cache import cache, FilingCache, StatsCache, CACHE_TTL

router = APIRouter()


@router.get("/", response_model=FilingList)
async def get_filings(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    form_type: Optional[str] = Query(None, description="Filter by form type (10-K, 10-Q, 8-K, S-1)"),
    ticker: Optional[str] = Query(None, description="Filter by company ticker"),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user_optional)  # 改为可选认证
):
    """
    Get list of filings with optional filters
    Results are cached for 5 minutes
    Authentication is optional - public endpoint
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
            company={
                "id": filing.company.id,
                "name": filing.company.name,
                "ticker": filing.company.ticker,
                "cik": filing.company.cik,
                "is_sp500": filing.company.is_sp500,  # 添加 S&P 500 标记
                "is_nasdaq100": filing.company.is_nasdaq100  # 添加 NASDAQ 100 标记
            },
            one_liner=filing.ai_summary[:100] + "..." if filing.ai_summary else None,
            sentiment=filing.management_tone.value if filing.management_tone else None,
            tags=filing.key_tags or [],
            vote_counts=vote_counts,
            comment_count=filing.comment_count or 0,
            view_count=view_count,  # 添加 view_count
            event_type=filing.event_type  # For 8-K
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
    include_charts: bool = Query(True, description="Include chart data in response"),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)  # 详情页仍需要认证
):
    """
    Get specific filing by ID with differentiated display support
    Returns type-specific fields based on filing_type
    Results are cached for 1 hour
    Enforces daily view limits for free users
    """
    # Check if user can view this filing
    view_check = ViewTrackingService.can_view_filing(db, current_user, filing_id)
    
    if not view_check["can_view"]:
        # Return limited info for users who hit their limit
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Daily limit reached. Upgrade to Pro for unlimited access.",
                "error": "DAILY_LIMIT_REACHED",
                "views_today": view_check["views_today"],
                "daily_limit": ViewTrackingService.DAILY_FREE_LIMIT,
                "upgrade_url": "/subscription"
            }
        )
    
    # Generate cache key (include charts parameter)
    cache_key = FilingCache.get_filing_detail_key(f"{filing_id}_charts_{include_charts}")
    
    # Try cache first
    cached_result = cache.get(cache_key)
    if cached_result:
        # Record view for free users (Pro users don't need tracking)
        if not view_check["is_pro"]:
            ViewTrackingService.record_view(db, current_user, filing_id)
        
        # Still increment view count even for cached results
        view_count = StatsCache.increment_view_count(str(filing_id))
        
        # Add view limit info to cached result
        cached_result["view_limit_info"] = {
            "views_remaining": view_check["views_remaining"],
            "is_pro": view_check["is_pro"],
            "views_today": view_check["views_today"]
        }
        
        # Add view count
        cached_result["view_count"] = view_count
        
        # Add user vote if authenticated
        if current_user:
            vote = db.query(UserVote).filter(
                UserVote.user_id == current_user.id,
                UserVote.filing_id == filing_id
            ).first()
            if vote:
                cached_result["user_vote"] = vote.vote_type
        
        return cached_result
    
    # Get from database
    filing = db.query(Filing).options(joinedload(Filing.company)).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    # Record view for ALL users (不管是否 Pro 用户)
    ViewTrackingService.record_view(db, current_user, filing_id)
    
    # Increment view count
    view_count = StatsCache.increment_view_count(str(filing_id))
    
    # Get user vote if authenticated
    user_vote = None
    if current_user:
        vote = db.query(UserVote).filter(
            UserVote.user_id == current_user.id,
            UserVote.filing_id == filing_id
        ).first()
        if vote:
            user_vote = vote.vote_type
    
    # Get vote counts from database
    vote_counts = {
        "bullish": filing.bullish_votes or 0,
        "neutral": filing.neutral_votes or 0,
        "bearish": filing.bearish_votes or 0
    }
    
    # Prepare base response data
    response_data = {
        "id": filing.id,
        "form_type": filing.filing_type.value,
        "filing_date": filing.filing_date,
        "accession_number": filing.accession_number,
        "file_url": filing.primary_doc_url or "",
        "cik": filing.company.cik,
        "company": {
            "id": filing.company.id,
            "name": filing.company.name,
            "ticker": filing.company.ticker,
            "cik": filing.company.cik,
            "is_sp500": filing.company.is_sp500,  # 添加 S&P 500 标记
            "is_nasdaq100": filing.company.is_nasdaq100  # 添加 NASDAQ 100 标记
        },
        "status": filing.status.value,
        "ai_summary": filing.ai_summary,
        "one_liner": filing.ai_summary[:100] + "..." if filing.ai_summary else None,
        "sentiment": filing.management_tone.value if filing.management_tone else None,
        "sentiment_explanation": filing.tone_explanation,
        "key_points": extract_key_points(filing),
        "risks": extract_risks(filing),
        "opportunities": extract_opportunities(filing),
        "questions_answers": filing.key_questions or [],
        "tags": filing.key_tags or [],
        # FIXED: financial_metrics now expects text narrative, not JSON
        "financial_metrics": filing.financial_highlights,  # This is now text
        "processed_at": filing.processing_completed_at,
        "created_at": filing.created_at,
        "updated_at": filing.updated_at,
        # Add interaction stats
        "vote_counts": vote_counts,
        "comment_count": filing.comment_count or 0,
        "view_count": view_count,  # 添加 view_count
        "user_vote": user_vote,
        # Add view limit info
        "view_limit_info": {
            "views_remaining": view_check["views_remaining"],
            "is_pro": view_check["is_pro"],
            "views_today": view_check["views_today"]
        },
        # Existing differentiated fields
        "specific_data": filing.filing_specific_data if filing.filing_specific_data else {},
        "chart_data": filing.chart_data if include_charts and filing.chart_data else None,
    }
    
    # Add common fields
    response_data.update({
        "fiscal_year": filing.fiscal_year,
        "fiscal_quarter": filing.fiscal_quarter,
        "period_end_date": filing.period_end_date,
    })
    
    # Add type-specific fields based on filing_type
    filing_type = filing.filing_type.value
    
    if filing_type == "10-K":
        response_data.update({
            "auditor_opinion": filing.auditor_opinion,
            "three_year_financials": filing.three_year_financials,
            "business_segments": filing.business_segments,
            "risk_summary": filing.risk_summary,
            "growth_drivers": filing.growth_drivers,
            "management_outlook": filing.management_outlook,
            "strategic_adjustments": filing.strategic_adjustments,
            "market_impact_10k": filing.market_impact_10k,
            "financial_highlights": filing.financial_highlights
        })
    
    elif filing_type == "10-Q":
        response_data.update({
            "expectations_comparison": filing.expectations_comparison,
            "cost_structure": filing.cost_structure,
            "guidance_update": filing.guidance_update,
            "growth_decline_analysis": filing.growth_decline_analysis,
            "management_tone_analysis": filing.management_tone_analysis,
            "beat_miss_analysis": filing.beat_miss_analysis,
            "market_impact_10q": filing.market_impact_10q,
            # FIXED: core_metrics now uses financial_highlights which is text
            "core_metrics": filing.financial_highlights  # This is now text (financial snapshot)
        })
    
    elif filing_type == "8-K":
        response_data.update({
            "item_type": filing.item_type,
            "items": filing.items,
            "event_timeline": filing.event_timeline,
            "event_nature_analysis": filing.event_nature_analysis,
            "market_impact_analysis": filing.market_impact_analysis,
            "key_considerations": filing.key_considerations,
            "event_type": filing.event_type,
            "event_summary": extract_event_summary(filing),
            "event_details": {  # For backward compatibility
                "type": filing.event_type,
                "items": filing.items
            }
        })
    
    elif filing_type == "S-1":
        response_data.update({
            "ipo_details": filing.ipo_details,
            "company_overview": filing.company_overview,
            "financial_summary": filing.financial_summary,
            "risk_categories": filing.risk_categories,
            "growth_path_analysis": filing.growth_path_analysis,
            "competitive_moat_analysis": filing.competitive_moat_analysis,
            "financial_highlights": filing.financial_highlights
        })
    
    # Cache the result without view_limit_info and user_vote (since they're user-specific)
    cache_data = response_data.copy()
    cache_data.pop("view_limit_info", None)
    cache_data.pop("user_vote", None)
    cache.set(cache_key, cache_data, ttl=CACHE_TTL["filing_detail"])
    
    return response_data


@router.get("/check-access/{filing_id}")
async def check_filing_access(
    filing_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Check if user can access a filing without recording a view
    Useful for UI to show lock/unlock status
    """
    view_check = ViewTrackingService.can_view_filing(db, current_user, filing_id)
    
    # Also get user's overall stats
    user_stats = ViewTrackingService.get_user_view_stats(db, current_user.id)
    
    return {
        "filing_id": filing_id,
        "can_view": view_check["can_view"],
        "reason": view_check["reason"],
        "user_stats": user_stats
    }


@router.get("/popular/{period}")
async def get_popular_filings(
    period: str = "day",  # day, week, month
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user_optional)  # 改为可选认证
):
    """
    Get popular filings based on view count
    Results are cached for 10 minutes
    Authentication is optional - public endpoint
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


# Helper functions
def extract_event_summary(filing: Filing) -> str:
    """Extract event summary from AI summary for 8-K"""
    # Use first paragraph of AI summary as event summary
    if filing.ai_summary:
        return filing.ai_summary.split('\n')[0]
    return None


def extract_key_points(filing: Filing) -> List[str]:
    """Extract key points from filing"""
    # TODO: Implement proper extraction logic
    # For now, return empty list
    return []


def extract_risks(filing: Filing) -> List[str]:
    """Extract risks from filing"""
    # TODO: Implement proper extraction logic
    # For now, return empty list
    return []


def extract_opportunities(filing: Filing) -> List[str]:
    """Extract opportunities from filing"""
    # TODO: Implement proper extraction logic
    # For now, return empty list
    return []
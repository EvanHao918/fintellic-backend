# app/api/endpoints/stats.py
"""
Statistics API endpoints for real-time community data
"""
from typing import List, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.api import deps
from app.models.filing import Filing, ProcessingStatus
from app.models.company import Company
from app.core.cache import cache, StatsCache, CACHE_TTL

router = APIRouter()


@router.get("/overview")
async def get_stats_overview(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Get overall platform statistics
    """
    # Generate cache key
    cache_key = "stats:overview"
    
    # Try cache first
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result
    
    # Calculate statistics
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    
    # Total filings
    total_filings = db.query(Filing).filter(
        Filing.status == ProcessingStatus.COMPLETED
    ).count()
    
    # Today's filings
    today_filings = db.query(Filing).filter(
        Filing.created_at >= today_start,
        Filing.status == ProcessingStatus.COMPLETED
    ).count()
    
    # This week's filings
    week_filings = db.query(Filing).filter(
        Filing.created_at >= week_start,
        Filing.status == ProcessingStatus.COMPLETED
    ).count()
    
    # Active companies (with filings)
    active_companies = db.query(func.count(func.distinct(Filing.company_id))).scalar()
    
    # Most active companies this week
    most_active = db.query(
        Company.ticker,
        Company.name,
        func.count(Filing.id).label('filing_count')
    ).join(
        Filing
    ).filter(
        Filing.created_at >= week_start,
        Filing.status == ProcessingStatus.COMPLETED
    ).group_by(
        Company.id, Company.ticker, Company.name
    ).order_by(
        desc('filing_count')
    ).limit(5).all()
    
    result = {
        "total_filings": total_filings,
        "today_filings": today_filings,
        "week_filings": week_filings,
        "active_companies": active_companies,
        "most_active_companies": [
            {
                "ticker": company.ticker,
                "name": company.name,
                "filing_count": company.filing_count
            }
            for company in most_active
        ],
        "updated_at": now.isoformat()
    }
    
    # Cache for 5 minutes
    cache.set(cache_key, result, ttl=300)
    
    return result


@router.get("/trending")
async def get_trending_filings(
    period: str = Query("day", regex="^(hour|day|week)$"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Get trending filings based on view velocity
    """
    # This is similar to popular filings but focuses on recent activity
    from app.api.endpoints.filings import get_popular_filings
    return await get_popular_filings(period, limit, db, current_user)


@router.get("/sentiment")
async def get_market_sentiment(
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Get overall market sentiment based on votes
    """
    # Generate cache key
    cache_key = f"stats:sentiment:{days}"
    
    # Try cache first
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result
    
    # Get filings from the last N days
    start_date = datetime.utcnow() - timedelta(days=days)
    
    filings = db.query(Filing).filter(
        Filing.created_at >= start_date,
        Filing.status == ProcessingStatus.COMPLETED
    ).all()
    
    # Aggregate votes
    total_bullish = 0
    total_bearish = 0
    sentiment_by_type = {}
    
    for filing in filings:
        votes = StatsCache.get_vote_counts(str(filing.id))
        total_bullish += votes.get("bullish", 0)
        total_bearish += votes.get("bearish", 0)
        
        # Group by filing type
        filing_type = filing.filing_type.value
        if filing_type not in sentiment_by_type:
            sentiment_by_type[filing_type] = {"bullish": 0, "bearish": 0}
        
        sentiment_by_type[filing_type]["bullish"] += votes.get("bullish", 0)
        sentiment_by_type[filing_type]["bearish"] += votes.get("bearish", 0)
    
    # Calculate percentages
    total_votes = total_bullish + total_bearish
    
    result = {
        "period_days": days,
        "total_votes": total_votes,
        "overall_sentiment": {
            "bullish": total_bullish,
            "bearish": total_bearish,
            "bullish_percentage": round(total_bullish / total_votes * 100, 1) if total_votes > 0 else 0,
            "bearish_percentage": round(total_bearish / total_votes * 100, 1) if total_votes > 0 else 0
        },
        "sentiment_by_type": sentiment_by_type,
        "updated_at": datetime.utcnow().isoformat()
    }
    
    # Cache for 10 minutes
    cache.set(cache_key, result, ttl=600)
    
    return result


@router.get("/activity/hourly")
async def get_hourly_activity(
    hours: int = Query(24, ge=1, le=168),  # Up to 1 week
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Get filing activity by hour
    """
    # Generate cache key
    cache_key = f"stats:activity:hourly:{hours}"
    
    # Try cache first
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result
    
    # Calculate hourly activity
    start_time = datetime.utcnow() - timedelta(hours=hours)
    
    # Get filings grouped by hour
    hourly_data = []
    for i in range(hours):
        hour_start = start_time + timedelta(hours=i)
        hour_end = hour_start + timedelta(hours=1)
        
        count = db.query(Filing).filter(
            Filing.created_at >= hour_start,
            Filing.created_at < hour_end,
            Filing.status == ProcessingStatus.COMPLETED
        ).count()
        
        hourly_data.append({
            "hour": hour_start.isoformat(),
            "filings": count
        })
    
    result = {
        "hours": hours,
        "data": hourly_data,
        "updated_at": datetime.utcnow().isoformat()
    }
    
    # Cache for 15 minutes
    cache.set(cache_key, result, ttl=900)
    
    return result


@router.get("/leaderboard")
async def get_community_leaderboard(
    period: str = Query("week", regex="^(day|week|month|all)$"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Get most viewed companies and filings
    """
    # Generate cache key
    cache_key = f"stats:leaderboard:{period}:{limit}"
    
    # Try cache first
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result
    
    # Calculate date range
    now = datetime.utcnow()
    if period == "day":
        start_date = now - timedelta(days=1)
    elif period == "week":
        start_date = now - timedelta(days=7)
    elif period == "month":
        start_date = now - timedelta(days=30)
    else:  # all
        start_date = datetime(2020, 1, 1)  # Arbitrary old date
    
    # Get filings from date range
    filings = db.query(Filing).filter(
        Filing.created_at >= start_date,
        Filing.status == ProcessingStatus.COMPLETED
    ).all()
    
    # Calculate most viewed filings
    filing_views = []
    company_views = {}
    
    for filing in filings:
        view_count = StatsCache.get_view_count(str(filing.id))
        if view_count > 0:
            filing_views.append({
                "filing": filing,
                "views": view_count
            })
            
            # Aggregate by company
            company_key = filing.company.ticker
            if company_key not in company_views:
                company_views[company_key] = {
                    "company": filing.company,
                    "views": 0,
                    "filings": 0
                }
            company_views[company_key]["views"] += view_count
            company_views[company_key]["filings"] += 1
    
    # Sort and limit
    filing_views.sort(key=lambda x: x["views"], reverse=True)
    top_filings = filing_views[:limit]
    
    company_list = list(company_views.values())
    company_list.sort(key=lambda x: x["views"], reverse=True)
    top_companies = company_list[:limit]
    
    result = {
        "period": period,
        "top_filings": [
            {
                "id": item["filing"].id,
                "company_ticker": item["filing"].company.ticker,
                "company_name": item["filing"].company.name,
                "form_type": item["filing"].filing_type.value,
                "filing_date": item["filing"].filing_date.isoformat(),
                "views": item["views"],
                "summary": item["filing"].ai_summary[:100] + "..." if item["filing"].ai_summary else None
            }
            for item in top_filings
        ],
        "top_companies": [
            {
                "ticker": item["company"].ticker,
                "name": item["company"].name,
                "total_views": item["views"],
                "filing_count": item["filings"],
                "avg_views_per_filing": round(item["views"] / item["filings"], 1)
            }
            for item in top_companies
        ],
        "updated_at": now.isoformat()
    }
    
    # Cache for 10 minutes
    cache.set(cache_key, result, ttl=600)
    
    return result
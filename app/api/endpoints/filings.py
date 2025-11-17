"""
Filing-related API endpoints with unified analysis support and enhanced company info
Handles both v1 (legacy) and v2 (unified) analysis formats
Enhanced to return full company details for mature companies
FIXED: Changed all file_url to filing_url
FIXED: Use getattr to safely access key_tags
ENHANCED: Return detected_at timestamps for accurate timing display
CRITICAL FIX: Corrected PostgreSQL ORDER BY syntax - NULLS LAST must come after DESC
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
import json

from app.api import deps
from app.models.filing import Filing, ProcessingStatus
from app.models.company import Company
from app.models import UserVote
from app.services.view_tracking import ViewTrackingService
from app.schemas.filing import FilingBrief, FilingDetail, FilingList
from app.core.cache import cache, FilingCache, StatsCache, CACHE_TTL

router = APIRouter()


def safe_json_to_string(value):
    """Convert JSON value to string safely, handling empty dicts"""
    if value is None:
        return None
    if isinstance(value, dict):
        if not value:  # Empty dict
            return None
        return json.dumps(value)
    if isinstance(value, str):
        return value if value else None
    return str(value) if value else None


def get_vote_counts_for_filing(db: Session, filing_id: int) -> Dict[str, int]:
    """
    Get vote counts for a filing from UserVote table
    Returns dict with bullish, neutral, bearish counts
    """
    # Get all votes for this filing
    votes = db.query(UserVote).filter(UserVote.filing_id == filing_id).all()
    
    # Count by type
    counts = {
        "bullish": 0,
        "neutral": 0,
        "bearish": 0
    }
    
    for vote in votes:
        if vote.vote_type in counts:
            counts[vote.vote_type] += 1
    
    return counts


def get_company_info_dict(company: Company, filing_type: str) -> dict:
    """
    获取公司信息字典，根据filing类型决定返回详细程度
    对于S-1返回基础信息，对于成熟公司返回完整信息
    """
    # 基础信息（所有公司都有）
    base_info = {
        "id": company.id,
        "name": company.name,
        "ticker": company.ticker or f"IPO-{company.cik[-4:]}",  # IPO公司可能没有ticker
        "cik": company.cik,
        "is_sp500": company.is_sp500,
        "is_nasdaq100": company.is_nasdaq100,
        "is_public": getattr(company, 'is_public', True),
        "has_s1_filing": getattr(company, 'has_s1_filing', False)
    }
    
    # 如果是S-1文件或公司数据不完整，只返回基础信息
    if filing_type == "S-1" or not company.ticker:
        base_info["company_type"] = "Pre-IPO" if filing_type == "S-1" else "Public Company"
        return base_info
    
    # 成熟公司返回完整信息
    full_info = base_info.copy()
    full_info.update({
        # 分类信息
        "legal_name": company.legal_name,
        "sector": getattr(company, 'sector', company.sic_description),  # 优先使用sector，否则用sic_description
        "industry": getattr(company, 'industry', None),
        "sic": company.sic,
        "sic_description": company.sic_description,
        
        # 位置信息
        "headquarters": getattr(company, 'headquarters', None),
        "country": getattr(company, 'country', 'United States'),
        "state": company.state,
        "state_of_incorporation": company.state_of_incorporation,
        
        # 公司详情
        "founded_year": getattr(company, 'founded_year', None),
        "employees": getattr(company, 'employees', None),
        "employee_size": company.employee_size_category if hasattr(company, 'employee_size_category') else None,
        "market_cap": getattr(company, 'market_cap', None),
        
        # 市场信息
        "exchange": company.exchange,
        "indices": company.indices_list if hasattr(company, 'indices_list') else [],
        "company_type": company.company_type if hasattr(company, 'company_type') else "Public Company",
        
        # 其他信息
        "website": getattr(company, 'website', None),
        "fiscal_year_end": company.fiscal_year_end,
        "business_phone": company.business_phone,
        
        # IPO相关
        "ipo_date": company.ipo_date.isoformat() if getattr(company, 'ipo_date', None) else None
    })
    
    # 移除None值以减少响应大小
    full_info = {k: v for k, v in full_info.items() if v is not None}
    
    return full_info


@router.get("/", response_model=FilingList)
async def get_filings(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    form_type: Optional[str] = Query(None, description="Filter by form type (10-K, 10-Q, 8-K, S-1)"),
    ticker: Optional[str] = Query(None, description="Filter by company ticker"),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user_optional)  # Optional authentication
):
    """
    Get list of filings with optional filters
    Results are cached for 5 minutes
    Authentication is optional - public endpoint
    Enhanced to return more company information and detected_at timestamps
    FIXED: Corrected PostgreSQL ORDER BY syntax
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
    if form_type and form_type != 'all':
        query = query.filter(Filing.form_type == form_type)
    if ticker:
        query = query.join(Company).filter(Company.ticker == ticker)
    
    # Only show completed filings
    query = query.filter(Filing.status == ProcessingStatus.COMPLETED)
    
    # Get total count
    total = query.count()
    
    # FIXED: Corrected PostgreSQL ORDER BY syntax - DESC must come before NULLS LAST
    query = query.order_by(
        desc(Filing.detected_at).nulls_last(),  # FIXED: Proper syntax
        desc(Filing.filing_date)
    )
    
    # Get paginated results
    filings = query.offset(skip).limit(limit).all()
    
    # Convert to response format
    filing_responses = []
    for filing in filings:
        # Get stats from cache
        view_count = StatsCache.get_view_count(str(filing.id))
        
        # Get vote counts from UserVote table
        vote_counts = get_vote_counts_for_filing(db, filing.id)
        
        # Use unified feed summary if available, fallback to legacy
        one_liner = filing.unified_feed_summary if filing.unified_feed_summary else (
            getattr(filing, 'ai_summary', '')[:100] + "..." if getattr(filing, 'ai_summary', None) else None
        )
        
        # 获取公司信息（Feed流使用简化版）
        company_info = get_company_info_dict(filing.company, filing.filing_type.value)
        
        # ENHANCED: Use detected_at for timing if available, fallback to filing_date
        display_time = filing.detected_at if filing.detected_at else filing.filing_date
        
        filing_brief = FilingBrief(
            id=filing.id,
            form_type=filing.filing_type.value,
            filing_date=display_time,  # ENHANCED: Use detected_at or filing_date
            detected_at=filing.detected_at,  # NEW: Include detected_at separately
            accession_number=filing.accession_number,
            filing_url=filing.primary_document_url or filing.filing_url or "",
            company=company_info,
            one_liner=one_liner,
            sentiment=filing.management_tone.value if filing.management_tone else None,
            tags=filing.key_tags if filing.key_tags else [],
            vote_counts=vote_counts,
            comment_count=getattr(filing, 'comment_count', 0) or 0,
            view_count=view_count,
            event_type=filing.event_type,  # For 8-K
            has_unified_analysis=filing.analysis_version == "v2" if filing.analysis_version else False
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

@router.get("/user/view-stats")
async def get_user_view_stats(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """Get user's view statistics"""
    return ViewTrackingService.get_user_view_stats(db, current_user.id)

@router.get("/{filing_id}", response_model=FilingDetail)
async def get_filing(
    filing_id: int,
    include_charts: bool = Query(True, description="Include chart data in response"),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)  # Requires authentication
):
    """
    Get specific filing by ID with unified analysis support
    Returns unified analysis if available (v2), otherwise legacy format
    Results are cached for 1 hour
    Enforces daily view limits for free users
    Enhanced to return full company details for mature companies and detected_at timestamps
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
        # Record view
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
    
    # Record view
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
    
    # Get vote counts from UserVote table
    vote_counts = get_vote_counts_for_filing(db, filing_id)
    
    # 获取增强的公司信息（详情页使用完整版）
    company_info = get_company_info_dict(filing.company, filing.filing_type.value)
    
    # ENHANCED: Use detected_at for timing if available
    display_time = filing.detected_at if filing.detected_at else filing.filing_date
    
    # Prepare base response data
    response_data = {
        "id": filing.id,
        "form_type": filing.filing_type.value,
        "filing_date": filing.filing_date,  # Keep original SEC filing date
        "detected_at": filing.detected_at,  # NEW: Include precise detection time
        "display_time": display_time,  # NEW: Time to use for display (detected_at preferred)
        "accession_number": filing.accession_number,
        "filing_url": filing.primary_document_url or filing.filing_url or "",
        "cik": filing.company.cik,
        "company": company_info,
        "status": filing.status.value,
        
        # ==================== UNIFIED ANALYSIS FIELDS ====================
        "unified_analysis": filing.unified_analysis,
        "unified_feed_summary": filing.unified_feed_summary,
        "analysis_version": filing.analysis_version,
        "smart_markup_data": filing.safe_json_get('smart_markup_data'),
        "analyst_expectations": filing.safe_json_get('analyst_expectations'),
        
        # ==================== LEGACY FIELDS ====================
        "ai_summary": getattr(filing, 'ai_summary', None),
        "one_liner": filing.unified_feed_summary or (getattr(filing, 'ai_summary', '')[:100] + "..." if getattr(filing, 'ai_summary', None) else None),
        "sentiment": filing.management_tone.value if filing.management_tone else None,
        "sentiment_explanation": getattr(filing, 'tone_explanation', None),
        "key_points": extract_key_points(filing),
        "risks": extract_risks(filing),
        "opportunities": extract_opportunities(filing),
        "questions_answers": filing.safe_json_get('key_questions', []) or [],
        "tags": filing.key_tags if filing.key_tags else [],
        "financial_metrics": safe_json_to_string(filing.financial_metrics),
        
        # Metadata
        "processed_at": filing.processing_completed_at,
        "created_at": filing.created_at,
        "updated_at": filing.updated_at,
        
        # Interaction stats
        "vote_counts": vote_counts,
        "comment_count": getattr(filing, 'comment_count', 0) or 0,
        "view_count": view_count,
        "user_vote": user_vote,
        
        # View limit info
        "view_limit_info": {
            "views_remaining": view_check["views_remaining"],
            "is_pro": view_check["is_pro"],
            "views_today": view_check["views_today"]
        },
        
        # Existing differentiated fields
        "specific_data": filing.safe_json_get('filing_specific_data', {}) or {},
        "chart_data": filing.safe_json_get('chart_data') if include_charts else None,
    }
    
    # Add common fields (safe access for potentially missing columns)
    response_data.update({
        "fiscal_year": getattr(filing, 'fiscal_year', None),
        "fiscal_quarter": getattr(filing, 'fiscal_quarter', None),
        "period_end_date": filing.period_end_date,
    })
    
    # Add type-specific fields based on filing_type
    filing_type = filing.filing_type.value
    
    if filing_type == "10-K":
        response_data.update({
            "auditor_opinion": getattr(filing, 'auditor_opinion', None),
            "three_year_financials": getattr(filing, 'three_year_financials', None),
            "business_segments": getattr(filing, 'business_segments', None),
            "risk_summary": getattr(filing, 'risk_summary', None),
            "growth_drivers": getattr(filing, 'growth_drivers', None),
            "management_outlook": getattr(filing, 'management_outlook', None),
            "strategic_adjustments": getattr(filing, 'strategic_adjustments', None),
            "market_impact_10k": getattr(filing, 'market_impact_10k', None),
            "financial_highlights": safe_json_to_string(filing.financial_highlights)
        })
    
    elif filing_type == "10-Q":
        response_data.update({
            "expectations_comparison": getattr(filing, 'expectations_comparison', None),
            "cost_structure": getattr(filing, 'cost_structure', None),
            "guidance_update": getattr(filing, 'guidance_update', None),
            "growth_decline_analysis": getattr(filing, 'growth_decline_analysis', None),
            "management_tone_analysis": getattr(filing, 'management_tone_analysis', None),
            "beat_miss_analysis": getattr(filing, 'beat_miss_analysis', None),
            "market_impact_10q": getattr(filing, 'market_impact_10q', None),
            # Use either core_metrics or financial_highlights
            "core_metrics": safe_json_to_string(filing.core_metrics) or safe_json_to_string(filing.financial_highlights),
            "financial_highlights": safe_json_to_string(filing.financial_highlights)
        })
    
    elif filing_type == "8-K":
        response_data.update({
            "item_type": getattr(filing, 'item_type', None),
            "items": getattr(filing, 'items', None),
            "event_timeline": getattr(filing, 'event_timeline', None),
            "event_nature_analysis": getattr(filing, 'event_nature_analysis', None),
            "market_impact_analysis": getattr(filing, 'market_impact_analysis', None),
            "key_considerations": getattr(filing, 'key_considerations', None),
            "event_type": filing.event_type,
            "event_summary": extract_event_summary(filing),
            "event_details": {
                "type": filing.event_type,
                "items": getattr(filing, 'items', None)
            }
        })
    
    elif filing_type == "S-1":
        response_data.update({
            "ipo_details": getattr(filing, 'ipo_details', None),
            "company_overview": getattr(filing, 'company_overview', None),
            "financial_summary": getattr(filing, 'financial_summary', None),
            "risk_categories": getattr(filing, 'risk_categories', None),
            "growth_path_analysis": getattr(filing, 'growth_path_analysis', None),
            "competitive_moat_analysis": getattr(filing, 'competitive_moat_analysis', None),
            "financial_highlights": safe_json_to_string(filing.financial_highlights)
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
    
    # Check if filing has unified analysis
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    has_unified_analysis = filing and filing.analysis_version == "v2"
    
    return {
        "filing_id": filing_id,
        "can_view": view_check["can_view"],
        "reason": view_check["reason"],
        "user_stats": user_stats,
        "has_unified_analysis": has_unified_analysis
    }


@router.get("/popular/{period}")
async def get_popular_filings(
    period: str = "day",  # day, week, month
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user_optional)
):
    """
    Get popular filings based on view count
    Results are cached for 10 minutes
    Authentication is optional - public endpoint
    Enhanced to return company information and detected_at timestamps
    FIXED: Corrected PostgreSQL ORDER BY syntax
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
    now = datetime.utcnow()
    
    if period == "day":
        start_date = now - timedelta(days=1)
    elif period == "week":
        start_date = now - timedelta(days=7)
    else:  # month
        start_date = now - timedelta(days=30)
    
    # FIXED: Use proper PostgreSQL syntax for ORDER BY with NULLS LAST
    filings = db.query(Filing).options(joinedload(Filing.company)).filter(
        Filing.detected_at >= start_date if Filing.detected_at else Filing.created_at >= start_date,
        Filing.status == ProcessingStatus.COMPLETED
    ).order_by(
        desc(Filing.detected_at).nulls_last(),  # FIXED: Proper syntax
        desc(Filing.created_at)
    ).limit(100).all()
    
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
        
        # Get vote counts from UserVote table
        vote_counts = get_vote_counts_for_filing(db, filing.id)
        
        # Use unified content if available
        summary = filing.unified_analysis[:200] + "..." if filing.unified_analysis else (
            getattr(filing, 'ai_summary', '')[:200] + "..." if getattr(filing, 'ai_summary', None) else None
        )
        
        # 获取公司基础信息
        company_info = {
            "ticker": filing.company.ticker,
            "name": filing.company.name,
            "is_sp500": filing.company.is_sp500,
            "is_nasdaq100": filing.company.is_nasdaq100,
            "sector": getattr(filing.company, 'sector', filing.company.sic_description)
        }
        
        # ENHANCED: Use detected_at for display if available
        display_time = filing.detected_at if filing.detected_at else filing.filing_date
        
        result.append({
            "id": filing.id,
            "company": company_info,
            "form_type": filing.filing_type.value,
            "filing_date": filing.filing_date.isoformat(),
            "detected_at": filing.detected_at.isoformat() if filing.detected_at else None,
            "display_time": display_time.isoformat(),
            "ai_summary": summary,
            "view_count": item["view_count"],
            "votes": vote_counts,
            "created_at": filing.created_at.isoformat(),
            "has_unified_analysis": filing.analysis_version == "v2"
        })
    
    # Cache the result
    cache.set(cache_key, result, ttl=CACHE_TTL["popular_filings"])
    
    return result


# Helper functions
def extract_event_summary(filing: Filing) -> str:
    """Extract event summary from AI summary for 8-K"""
    # Use unified analysis if available
    if filing.unified_analysis:
        # Take first paragraph
        return filing.unified_analysis.split('\n')[0]
    elif getattr(filing, 'ai_summary', None):
        return filing.ai_summary.split('\n')[0]
    return None


def extract_key_points(filing: Filing) -> List[str]:
    """Extract key points from filing"""
    # Check new field first
    if filing.key_points:
        if isinstance(filing.key_points, list):
            return filing.key_points
        elif isinstance(filing.key_points, dict) and not filing.key_points:  # Empty dict
            return []
    
    # If we have smart markup data, extract key insights
    smart_data = filing.safe_json_get('smart_markup_data')
    if smart_data and isinstance(smart_data, dict) and smart_data.get('insights'):
        return smart_data['insights']
    
    return []


def extract_risks(filing: Filing) -> List[str]:
    """Extract risks from filing"""
    # Check new field first
    if filing.risks:
        if isinstance(filing.risks, list):
            return filing.risks
        elif isinstance(filing.risks, dict) and not filing.risks:  # Empty dict
            return []
    
    # If we have smart markup data, extract negative items
    smart_data = filing.safe_json_get('smart_markup_data')
    if smart_data and isinstance(smart_data, dict) and smart_data.get('negative'):
        return smart_data['negative']
    
    return []


def extract_opportunities(filing: Filing) -> List[str]:
    """Extract opportunities from filing"""
    # Check new field first
    if filing.opportunities:
        if isinstance(filing.opportunities, list):
            return filing.opportunities
        elif isinstance(filing.opportunities, dict) and not filing.opportunities:  # Empty dict
            return []
    
    # If we have smart markup data, extract positive items
    smart_data = filing.safe_json_get('smart_markup_data')
    if smart_data and isinstance(smart_data, dict) and smart_data.get('positive'):
        return smart_data['positive']
    
    return []
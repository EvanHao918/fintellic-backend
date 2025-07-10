# app/api/endpoints/watchlist.py
"""
Watchlist API endpoints for user's favorite companies
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, exists, or_, func

from app.api import deps
from app.models.company import Company
from app.models.user import User
from app.models.watchlist import Watchlist
from app.models.filing import Filing
from app.core.cache import cache
from app.schemas.watchlist import (
    WatchlistResponse, 
    WatchlistAddResponse, 
    WatchlistRemoveResponse,
    WatchlistStatusResponse,
    WatchlistCountResponse,
    WatchedCompany,
    CompanySearchResult
)
import json
from datetime import datetime

router = APIRouter()


@router.get("/", response_model=List[WatchedCompany])
async def get_watchlist(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
) -> List[WatchedCompany]:
    """
    Get current user's watchlist with company details
    """
    # Try cache first
    cache_key = f"watchlist:user:{current_user.id}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return json.loads(cached_result)
    
    # Get watchlist entries with company details
    watchlist_entries = db.query(Watchlist).filter(
        Watchlist.user_id == current_user.id
    ).options(
        joinedload(Watchlist.company)
    ).order_by(Watchlist.added_at.desc()).all()
    
    # Format response
    result = []
    for entry in watchlist_entries:
        company = entry.company
        
        # Get latest filing for this company
        latest_filing = db.query(Filing).filter(
            Filing.company_id == company.id
        ).order_by(Filing.filing_date.desc()).first()
        
        watched_company = {
            "ticker": company.ticker,
            "name": company.name,
            "sector": company.sic_description,
            "industry": None,  # Company model doesn't have business_description
            "is_sp500": company.is_sp500,
            "is_nasdaq100": company.is_nasdaq100,
            "indices": company.indices_list,
            "added_at": entry.added_at.isoformat(),
            "last_filing": None
        }
        
        if latest_filing:
            watched_company["last_filing"] = {
                "filing_type": latest_filing.filing_type.value,
                "filing_date": latest_filing.filing_date.isoformat(),
                "sentiment": None  # Filing model doesn't have sentiment field
            }
        
        result.append(watched_company)
    
    # Cache for 5 minutes
    cache.set(cache_key, json.dumps(result, default=str), ttl=300)
    
    return result


@router.post("/{ticker}", response_model=WatchlistAddResponse)
async def add_to_watchlist(
    ticker: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
) -> WatchlistAddResponse:
    """
    Add a company to user's watchlist
    """
    ticker = ticker.upper()
    
    # Verify company exists and is watchable
    company = db.query(Company).filter(
        Company.ticker == ticker
    ).first()
    
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {ticker} not found"
        )
    
    if not company.is_watchable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{ticker} is not in S&P 500 or NASDAQ 100"
        )
    
    # Check if already in watchlist
    existing = db.query(Watchlist).filter(
        and_(
            Watchlist.user_id == current_user.id,
            Watchlist.company_id == company.id
        )
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{ticker} is already in your watchlist"
        )
    
    # Add to watchlist (no limit check since all users have unlimited)
    watchlist_entry = Watchlist(
        user_id=current_user.id,
        company_id=company.id
    )
    db.add(watchlist_entry)
    db.commit()
    
    # Clear cache
    cache_key = f"watchlist:user:{current_user.id}"
    cache.delete(cache_key)
    
    # Get current count
    watchlist_count = db.query(Watchlist).filter(
        Watchlist.user_id == current_user.id
    ).count()
    
    return WatchlistAddResponse(
        message=f"{ticker} added to watchlist",
        ticker=company.ticker,
        name=company.name,
        watchlist_count=watchlist_count
    )


@router.delete("/{ticker}", response_model=WatchlistRemoveResponse)
async def remove_from_watchlist(
    ticker: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
) -> WatchlistRemoveResponse:
    """
    Remove a company from user's watchlist
    """
    ticker = ticker.upper()
    
    # Find company
    company = db.query(Company).filter(
        Company.ticker == ticker
    ).first()
    
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {ticker} not found"
        )
    
    # Find watchlist entry
    watchlist_entry = db.query(Watchlist).filter(
        and_(
            Watchlist.user_id == current_user.id,
            Watchlist.company_id == company.id
        )
    ).first()
    
    if not watchlist_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{ticker} not found in your watchlist"
        )
    
    # Remove from watchlist
    db.delete(watchlist_entry)
    db.commit()
    
    # Clear cache
    cache_key = f"watchlist:user:{current_user.id}"
    cache.delete(cache_key)
    
    # Get current count
    watchlist_count = db.query(Watchlist).filter(
        Watchlist.user_id == current_user.id
    ).count()
    
    return WatchlistRemoveResponse(
        message=f"{ticker} removed from watchlist",
        ticker=ticker,
        watchlist_count=watchlist_count
    )


@router.get("/check/{ticker}", response_model=WatchlistStatusResponse)
async def check_watchlist_status(
    ticker: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
) -> WatchlistStatusResponse:
    """
    Check if a company is in user's watchlist
    """
    ticker = ticker.upper()
    
    # Find company
    company = db.query(Company).filter(
        Company.ticker == ticker
    ).first()
    
    if not company:
        return WatchlistStatusResponse(
            ticker=ticker,
            is_watchlisted=False,
            watchlist_count=0
        )
    
    # Check if in watchlist
    is_watchlisted = db.query(exists().where(
        and_(
            Watchlist.user_id == current_user.id,
            Watchlist.company_id == company.id
        )
    )).scalar()
    
    # Get total count
    watchlist_count = db.query(Watchlist).filter(
        Watchlist.user_id == current_user.id
    ).count()
    
    return WatchlistStatusResponse(
        ticker=ticker,
        is_watchlisted=is_watchlisted,
        watchlist_count=watchlist_count
    )


@router.get("/count", response_model=WatchlistCountResponse)
async def get_watchlist_count(
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
) -> WatchlistCountResponse:
    """
    Get watchlist count and limit for user
    """
    count = db.query(Watchlist).filter(
        Watchlist.user_id == current_user.id
    ).count()
    
    return WatchlistCountResponse(
        count=count,
        limit=None,  # No limits for any user
        is_pro=current_user.tier == 'pro'
    )


@router.delete("/clear/all")
async def clear_watchlist(
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
) -> dict:
    """
    Clear entire watchlist
    """
    # Count entries before deletion
    count = db.query(Watchlist).filter(
        Watchlist.user_id == current_user.id
    ).count()
    
    # Delete all entries
    db.query(Watchlist).filter(
        Watchlist.user_id == current_user.id
    ).delete()
    
    db.commit()
    
    # Clear cache
    cache_key = f"watchlist:user:{current_user.id}"
    cache.delete(cache_key)
    
    return {
        "message": "Watchlist cleared",
        "removed_count": count
    }


@router.get("/search", response_model=List[CompanySearchResult])
async def search_watchable_companies(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=50, description="Maximum results"),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
) -> List[CompanySearchResult]:
    """
    Search for companies in S&P 500 or NASDAQ 100 to add to watchlist
    """
    search_term = f"%{q.upper()}%"
    
    # Search in watchable companies (S&P 500 or NASDAQ 100)
    companies = db.query(Company).filter(
        and_(
            or_(
                Company.ticker.ilike(search_term),
                Company.name.ilike(f"%{q}%")
            ),
            or_(
                Company.is_sp500 == True,
                Company.is_nasdaq100 == True
            )
        )
    ).order_by(
        # Exact ticker match first
        Company.ticker == q.upper(),
        # Then ticker starts with
        Company.ticker.ilike(f"{q.upper()}%"),
        # Then alphabetical
        Company.ticker
    ).limit(limit).all()
    
    # Get user's current watchlist
    user_watchlist_ids = db.query(Watchlist.company_id).filter(
        Watchlist.user_id == current_user.id
    ).subquery()
    
    # Format results
    results = []
    for company in companies:
        is_watchlisted = db.query(exists().where(
            and_(
                Watchlist.user_id == current_user.id,
                Watchlist.company_id == company.id
            )
        )).scalar()
        
        results.append(CompanySearchResult(
            ticker=company.ticker,
            name=company.name,
            sector=company.sic_description,
            is_sp500=company.is_sp500,
            is_nasdaq100=company.is_nasdaq100,
            indices=company.indices_list,
            is_watchlisted=is_watchlisted
        ))
    
    return results
# app/api/endpoints/watchlist.py
"""
Watchlist API endpoints for user's favorite companies
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, exists

from app.api import deps
from app.models.company import Company
from app.models.user import User
from app.core.cache import cache
import json
from datetime import datetime

router = APIRouter()

# In-memory storage for watchlist (temporary solution)
# In production, you should create a proper database table
USER_WATCHLISTS = {}


@router.get("/", response_model=List[dict])
async def get_watchlist(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
) -> List[dict]:
    """
    Get current user's watchlist
    """
    # Try cache first
    cache_key = f"watchlist:user:{current_user.id}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return json.loads(cached_result)
    
    # Get from in-memory storage (replace with database query in production)
    user_watchlist = USER_WATCHLISTS.get(current_user.id, [])
    
    # Get company details for each ticker in watchlist
    result = []
    for ticker in user_watchlist:
        company = db.query(Company).filter(
            Company.ticker == ticker
        ).first()
        
        if company:
            result.append({
                "ticker": company.ticker,
                "name": company.name,
                "sector": company.sector,
                "industry": company.industry,
                "added_at": datetime.utcnow().isoformat()  # In production, store this in DB
            })
    
    # Cache for 5 minutes
    cache.set(cache_key, json.dumps(result), ttl=300)
    
    return result


@router.post("/{ticker}")
async def add_to_watchlist(
    ticker: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
) -> dict:
    """
    Add a company to user's watchlist
    """
    ticker = ticker.upper()
    
    # Verify company exists
    company = db.query(Company).filter(
        Company.ticker == ticker
    ).first()
    
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {ticker} not found"
        )
    
    # Get current watchlist
    if current_user.id not in USER_WATCHLISTS:
        USER_WATCHLISTS[current_user.id] = []
    
    # Check if already in watchlist
    if ticker in USER_WATCHLISTS[current_user.id]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{ticker} is already in your watchlist"
        )
    
    # Check watchlist limit for free users
    if not current_user.is_pro and len(USER_WATCHLISTS[current_user.id]) >= 10:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Free users can only watch up to 10 companies. Upgrade to Pro for unlimited watchlist."
        )
    
    # Add to watchlist
    USER_WATCHLISTS[current_user.id].append(ticker)
    
    # Clear cache
    cache_key = f"watchlist:user:{current_user.id}"
    cache.delete(cache_key)
    
    return {
        "message": f"{ticker} added to watchlist",
        "ticker": company.ticker,
        "name": company.name,
        "watchlist_count": len(USER_WATCHLISTS[current_user.id])
    }


@router.delete("/{ticker}")
async def remove_from_watchlist(
    ticker: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
) -> dict:
    """
    Remove a company from user's watchlist
    """
    ticker = ticker.upper()
    
    # Get current watchlist
    if current_user.id not in USER_WATCHLISTS:
        USER_WATCHLISTS[current_user.id] = []
    
    # Check if in watchlist
    if ticker not in USER_WATCHLISTS[current_user.id]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{ticker} not found in your watchlist"
        )
    
    # Remove from watchlist
    USER_WATCHLISTS[current_user.id].remove(ticker)
    
    # Clear cache
    cache_key = f"watchlist:user:{current_user.id}"
    cache.delete(cache_key)
    
    return {
        "message": f"{ticker} removed from watchlist",
        "ticker": ticker,
        "watchlist_count": len(USER_WATCHLISTS[current_user.id])
    }


@router.get("/check/{ticker}")
async def check_watchlist_status(
    ticker: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
) -> dict:
    """
    Check if a company is in user's watchlist
    """
    ticker = ticker.upper()
    
    # Get current watchlist
    user_watchlist = USER_WATCHLISTS.get(current_user.id, [])
    is_watchlisted = ticker in user_watchlist
    
    return {
        "ticker": ticker,
        "is_watchlisted": is_watchlisted,
        "watchlist_count": len(user_watchlist)
    }


@router.get("/count")
async def get_watchlist_count(
    current_user: User = Depends(deps.get_current_user)
) -> dict:
    """
    Get watchlist count and limit for user
    """
    user_watchlist = USER_WATCHLISTS.get(current_user.id, [])
    
    return {
        "count": len(user_watchlist),
        "limit": None if current_user.is_pro else 10,
        "is_pro": current_user.is_pro
    }


@router.delete("/clear/all")
async def clear_watchlist(
    current_user: User = Depends(deps.get_current_user)
) -> dict:
    """
    Clear entire watchlist
    """
    if current_user.id in USER_WATCHLISTS:
        count = len(USER_WATCHLISTS[current_user.id])
        USER_WATCHLISTS[current_user.id] = []
        
        # Clear cache
        cache_key = f"watchlist:user:{current_user.id}"
        cache.delete(cache_key)
        
        return {
            "message": "Watchlist cleared",
            "removed_count": count
        }
    
    return {
        "message": "Watchlist was already empty",
        "removed_count": 0
    }
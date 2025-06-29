"""
User interaction endpoints - votes, comments, watchlist
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from pydantic import BaseModel

from app.api import deps
from app.core.database import get_db
from app.models.filing import Filing
from app.models.company import Company
from app.models.user import User

router = APIRouter()


# Request/Response schemas
class VoteRequest(BaseModel):
    sentiment: str  # "bullish", "neutral", or "bearish"


class VoteResponse(BaseModel):
    message: str
    vote_counts: dict


class CommentCreate(BaseModel):
    content: str


class CommentResponse(BaseModel):
    id: int
    user_id: int
    username: str
    content: str
    created_at: datetime


class WatchResponse(BaseModel):
    message: str
    is_watching: bool


# Voting endpoints
@router.post("/filings/{filing_id}/vote", response_model=VoteResponse)
async def vote_on_filing(
    filing_id: int,
    vote_request: VoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Vote on a filing's sentiment
    """
    # Validate sentiment
    valid_sentiments = ["bullish", "neutral", "bearish"]
    if vote_request.sentiment not in valid_sentiments:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sentiment. Must be one of: {valid_sentiments}"
        )
    
    # Get filing
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    # TODO: Check if user already voted (requires UserVote table)
    # For now, just update the vote count
    
    # Update vote count
    if vote_request.sentiment == "bullish":
        filing.bullish_votes = (filing.bullish_votes or 0) + 1
    elif vote_request.sentiment == "neutral":
        filing.neutral_votes = (filing.neutral_votes or 0) + 1
    else:  # bearish
        filing.bearish_votes = (filing.bearish_votes or 0) + 1
    
    db.commit()
    
    return VoteResponse(
        message=f"Successfully voted {vote_request.sentiment}",
        vote_counts={
            "bullish": filing.bullish_votes or 0,
            "neutral": filing.neutral_votes or 0,
            "bearish": filing.bearish_votes or 0
        }
    )


@router.get("/filings/{filing_id}/votes")
async def get_filing_votes(
    filing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get vote counts for a filing
    """
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    return {
        "filing_id": filing_id,
        "vote_counts": {
            "bullish": filing.bullish_votes or 0,
            "neutral": filing.neutral_votes or 0,
            "bearish": filing.bearish_votes or 0
        },
        "total_votes": (filing.bullish_votes or 0) + (filing.neutral_votes or 0) + (filing.bearish_votes or 0)
    }


# Comment endpoints (placeholder - requires Comment model)
@router.get("/filings/{filing_id}/comments")
async def get_filing_comments(
    filing_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get comments for a filing (placeholder)
    """
    # TODO: Implement when Comment model is available
    return {
        "filing_id": filing_id,
        "total": 0,
        "skip": skip,
        "limit": limit,
        "data": [],
        "message": "Comment feature coming soon"
    }


@router.post("/filings/{filing_id}/comments")
async def create_comment(
    filing_id: int,
    comment: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Create a comment on a filing (placeholder)
    """
    # Verify filing exists
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    # TODO: Implement when Comment model is available
    return {
        "message": "Comment feature coming soon",
        "content": comment.content
    }


# Watchlist endpoints (placeholder - requires UserWatchlist model)
@router.post("/companies/{ticker}/watch", response_model=WatchResponse)
async def watch_company(
    ticker: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Add company to watchlist (placeholder)
    """
    # Verify company exists
    company = db.query(Company).filter(Company.ticker == ticker.upper()).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # TODO: Implement when UserWatchlist model is available
    return WatchResponse(
        message=f"Added {ticker} to watchlist (feature coming soon)",
        is_watching=True
    )


@router.delete("/companies/{ticker}/watch", response_model=WatchResponse)
async def unwatch_company(
    ticker: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Remove company from watchlist (placeholder)
    """
    # Verify company exists
    company = db.query(Company).filter(Company.ticker == ticker.upper()).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # TODO: Implement when UserWatchlist model is available
    return WatchResponse(
        message=f"Removed {ticker} from watchlist (feature coming soon)",
        is_watching=False
    )


# User data endpoints
@router.get("/users/me/watchlist")
async def get_my_watchlist(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get current user's watchlist (placeholder)
    """
    # TODO: Implement when UserWatchlist model is available
    return {
        "user_id": current_user.id,
        "total": 0,
        "companies": [],
        "message": "Watchlist feature coming soon"
    }


@router.get("/users/me/history")
async def get_my_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get current user's filing view history (placeholder)
    """
    # TODO: Implement when UserHistory model is available
    return {
        "user_id": current_user.id,
        "total": 0,
        "skip": skip,
        "limit": limit,
        "data": [],
        "message": "History tracking coming soon"
    }
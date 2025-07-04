"""
User interaction endpoints - votes, comments, watchlist
"""
from typing import List, Optional, Dict
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from pydantic import BaseModel

from app.api import deps
from app.core.database import get_db
from app.models import User, Filing, Company, UserVote, VoteType

router = APIRouter()


# Request/Response schemas
class VoteRequest(BaseModel):
    sentiment: str  # "bullish", "neutral", or "bearish"


class VoteResponse(BaseModel):
    message: str
    vote_counts: Dict[str, int]
    user_vote: Optional[str] = None  # The user's current vote


class WatchResponse(BaseModel):
    message: str
    is_watching: bool


@router.post("/filings/{filing_id}/vote", response_model=VoteResponse)
async def vote_on_filing(
    filing_id: int,
    vote_request: VoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Vote on a filing's sentiment
    Users can only vote once per filing, but can change their vote
    """
    # Validate sentiment
    valid_sentiments = ["bullish", "neutral", "bearish"]
    if vote_request.sentiment not in valid_sentiments:
        raise HTTPException(
            status_code=400,
            f"Invalid sentiment. Must be one of: {valid_sentiments}"
        )
    
    # Get filing
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    # Check if user already voted
    existing_vote = db.query(UserVote).filter(
        UserVote.user_id == current_user.id,
        UserVote.filing_id == filing_id
    ).first()
    
    # Convert sentiment to VoteType
    vote_type = VoteType(vote_request.sentiment)
    
    if existing_vote:
        # User is changing their vote
        old_vote_type = existing_vote.vote_type
        
        # Decrease old vote count
        if old_vote_type == VoteType.BULLISH:
            filing.bullish_votes = max(0, (filing.bullish_votes or 0) - 1)
        elif old_vote_type == VoteType.NEUTRAL:
            filing.neutral_votes = max(0, (filing.neutral_votes or 0) - 1)
        else:  # bearish
            filing.bearish_votes = max(0, (filing.bearish_votes or 0) - 1)
        
        # Update vote type
        existing_vote.vote_type = vote_type
        message = f"Vote changed from {old_vote_type.value} to {vote_type.value}"
    else:
        # Create new vote record
        new_vote = UserVote(
            user_id=current_user.id,
            filing_id=filing_id,
            vote_type=vote_type
        )
        db.add(new_vote)
        message = f"Successfully voted {vote_type.value}"
    
    # Increase new vote count
    if vote_type == VoteType.BULLISH:
        filing.bullish_votes = (filing.bullish_votes or 0) + 1
    elif vote_type == VoteType.NEUTRAL:
        filing.neutral_votes = (filing.neutral_votes or 0) + 1
    else:  # bearish
        filing.bearish_votes = (filing.bearish_votes or 0) + 1
    
    db.commit()
    
    return VoteResponse(
        message=message,
        vote_counts={
            "bullish": filing.bullish_votes or 0,
            "neutral": filing.neutral_votes or 0,
            "bearish": filing.bearish_votes or 0
        },
        user_vote=vote_type.value
    )


@router.get("/filings/{filing_id}/votes")
async def get_filing_votes(
    filing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get vote counts for a filing and user's vote if any
    """
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    # Check if current user has voted
    user_vote = db.query(UserVote).filter(
        UserVote.user_id == current_user.id,
        UserVote.filing_id == filing_id
    ).first()
    
    return {
        "filing_id": filing_id,
        "vote_counts": {
            "bullish": filing.bullish_votes or 0,
            "neutral": filing.neutral_votes or 0,
            "bearish": filing.bearish_votes or 0
        },
        "total_votes": (filing.bullish_votes or 0) + (filing.neutral_votes or 0) + (filing.bearish_votes or 0),
        "user_vote": user_vote.vote_type.value if user_vote else None
    }


@router.delete("/filings/{filing_id}/vote")
async def remove_vote(
    filing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Remove user's vote from a filing
    """
    # Get user's vote
    user_vote = db.query(UserVote).filter(
        UserVote.user_id == current_user.id,
        UserVote.filing_id == filing_id
    ).first()
    
    if not user_vote:
        raise HTTPException(status_code=404, detail="No vote found for this filing")
    
    # Get filing to update counts
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    # Decrease vote count
    if user_vote.vote_type == VoteType.BULLISH:
        filing.bullish_votes = max(0, (filing.bullish_votes or 0) - 1)
    elif user_vote.vote_type == VoteType.NEUTRAL:
        filing.neutral_votes = max(0, (filing.neutral_votes or 0) - 1)
    else:  # bearish
        filing.bearish_votes = max(0, (filing.bearish_votes or 0) - 1)
    
    # Delete vote record
    db.delete(user_vote)
    db.commit()
    
    return {"message": "Vote removed successfully"}
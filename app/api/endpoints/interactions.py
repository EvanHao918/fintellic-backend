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
    print(f"[DEBUG] Vote request: filing_id={filing_id}, user_id={current_user.id}, sentiment={vote_request.sentiment}")
    
    # Validate sentiment
    valid_sentiments = ["bullish", "neutral", "bearish"]
    if vote_request.sentiment.lower() not in valid_sentiments:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sentiment. Must be one of: {valid_sentiments}"
        )
    
    # Get filing
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    print(f"[DEBUG] Current vote counts - Bullish: {filing.bullish_votes}, Neutral: {filing.neutral_votes}, Bearish: {filing.bearish_votes}")
    
    # Check if user already voted
    existing_vote = db.query(UserVote).filter(
        UserVote.user_id == current_user.id,
        UserVote.filing_id == filing_id
    ).first()
    
    # Use lowercase sentiment directly
    sentiment_lower = vote_request.sentiment.lower()
    
    if existing_vote:
        print(f"[DEBUG] User already voted: {existing_vote.vote_type}")
        
        # Check if it's the same vote
        if existing_vote.vote_type == sentiment_lower:
            # Same vote, no change needed
            print(f"[DEBUG] Same vote, no change")
            message = f"You already voted {sentiment_lower}"
        else:
            print(f"[DEBUG] Changing vote from {existing_vote.vote_type} to {sentiment_lower}")
            # Decrease old vote count
            if existing_vote.vote_type == "bullish":
                filing.bullish_votes = max(0, (filing.bullish_votes or 0) - 1)
            elif existing_vote.vote_type == "neutral":
                filing.neutral_votes = max(0, (filing.neutral_votes or 0) - 1)
            else:  # bearish
                filing.bearish_votes = max(0, (filing.bearish_votes or 0) - 1)
            
            # Increase new vote count
            if sentiment_lower == "bullish":
                filing.bullish_votes = (filing.bullish_votes or 0) + 1
            elif sentiment_lower == "neutral":
                filing.neutral_votes = (filing.neutral_votes or 0) + 1
            else:  # bearish
                filing.bearish_votes = (filing.bearish_votes or 0) + 1
            
            # Update vote type
            existing_vote.vote_type = sentiment_lower
            message = f"Vote changed from {existing_vote.vote_type} to {sentiment_lower}"
    else:
        print(f"[DEBUG] New vote: {sentiment_lower}")
        # Create new vote record
        new_vote = UserVote(
            user_id=current_user.id,
            filing_id=filing_id,
            vote_type=sentiment_lower  # 使用小写字符串
        )
        db.add(new_vote)
        
        # Increase vote count for new vote only
        if sentiment_lower == "bullish":
            filing.bullish_votes = (filing.bullish_votes or 0) + 1
        elif sentiment_lower == "neutral":
            filing.neutral_votes = (filing.neutral_votes or 0) + 1
        else:  # bearish
            filing.bearish_votes = (filing.bearish_votes or 0) + 1
            
        message = f"Successfully voted {sentiment_lower}"
    
    print(f"[DEBUG] Before commit - Bullish: {filing.bullish_votes}, Neutral: {filing.neutral_votes}, Bearish: {filing.bearish_votes}")
    
    try:
        db.commit()
        print("[DEBUG] Commit successful")
    except Exception as e:
        print(f"[ERROR] Commit failed: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save vote")
    
    # Verify vote was saved
    saved_vote = db.query(UserVote).filter(
        UserVote.user_id == current_user.id,
        UserVote.filing_id == filing_id
    ).first()
    
    if saved_vote:
        print(f"[SUCCESS] Vote saved: user_id={saved_vote.user_id}, filing_id={saved_vote.filing_id}, vote={saved_vote.vote_type}")
    else:
        print(f"[ERROR] Vote NOT saved for user_id={current_user.id}, filing_id={filing_id}")
    
    print(f"[DEBUG] Returning message: {message}")
    
    return VoteResponse(
        message=message,
        vote_counts={
            "bullish": filing.bullish_votes or 0,
            "neutral": filing.neutral_votes or 0,
            "bearish": filing.bearish_votes or 0
        },
        user_vote=sentiment_lower
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
    
    print(f"[DEBUG] Get votes - user_id={current_user.id}, filing_id={filing_id}, user_vote={user_vote.vote_type if user_vote else None}")
    
    return {
        "filing_id": filing_id,
        "vote_counts": {
            "bullish": filing.bullish_votes or 0,
            "neutral": filing.neutral_votes or 0,
            "bearish": filing.bearish_votes or 0
        },
        "total_votes": (filing.bullish_votes or 0) + (filing.neutral_votes or 0) + (filing.bearish_votes or 0),
        "user_vote": user_vote.vote_type if user_vote else None
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
    if user_vote.vote_type == "bullish":
        filing.bullish_votes = max(0, (filing.bullish_votes or 0) - 1)
    elif user_vote.vote_type == "neutral":
        filing.neutral_votes = max(0, (filing.neutral_votes or 0) - 1)
    else:  # bearish
        filing.bearish_votes = max(0, (filing.bearish_votes or 0) - 1)
    
    # Delete vote record
    db.delete(user_vote)
    db.commit()
    
    return {"message": "Vote removed successfully"}
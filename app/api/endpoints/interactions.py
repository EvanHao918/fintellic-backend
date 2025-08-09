"""
User interaction endpoints - votes, comments, watchlist
FIXED: Removed references to deprecated filing vote count fields
Now uses UserVote table for all vote management
"""
from typing import List, Optional, Dict
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func
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
    
    # Get current vote counts from UserVote table
    vote_counts = get_vote_counts_for_filing(db, filing_id)
    print(f"[DEBUG] Current vote counts - Bullish: {vote_counts['bullish']}, Neutral: {vote_counts['neutral']}, Bearish: {vote_counts['bearish']}")
    
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
            old_vote = existing_vote.vote_type
            print(f"[DEBUG] Changing vote from {old_vote} to {sentiment_lower}")
            
            # Update vote type
            existing_vote.vote_type = sentiment_lower
            existing_vote.created_at = datetime.utcnow()  # Update timestamp
            message = f"Vote changed from {old_vote} to {sentiment_lower}"
    else:
        print(f"[DEBUG] New vote: {sentiment_lower}")
        # Create new vote record
        new_vote = UserVote(
            user_id=current_user.id,
            filing_id=filing_id,
            vote_type=sentiment_lower  # 使用小写字符串
        )
        db.add(new_vote)
        message = f"Successfully voted {sentiment_lower}"
    
    try:
        db.commit()
        print("[DEBUG] Commit successful")
    except Exception as e:
        print(f"[ERROR] Commit failed: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save vote")
    
    # Get updated vote counts
    updated_counts = get_vote_counts_for_filing(db, filing_id)
    print(f"[DEBUG] After commit - Bullish: {updated_counts['bullish']}, Neutral: {updated_counts['neutral']}, Bearish: {updated_counts['bearish']}")
    
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
        vote_counts=updated_counts,
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
    
    # Get vote counts from UserVote table
    vote_counts = get_vote_counts_for_filing(db, filing_id)
    
    # Check if current user has voted
    user_vote = db.query(UserVote).filter(
        UserVote.user_id == current_user.id,
        UserVote.filing_id == filing_id
    ).first()
    
    print(f"[DEBUG] Get votes - user_id={current_user.id}, filing_id={filing_id}, user_vote={user_vote.vote_type if user_vote else None}")
    
    return {
        "filing_id": filing_id,
        "vote_counts": vote_counts,
        "total_votes": sum(vote_counts.values()),
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
    
    # Get filing to ensure it exists
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    vote_type = user_vote.vote_type
    
    # Delete vote record
    db.delete(user_vote)
    db.commit()
    
    # Get updated counts
    updated_counts = get_vote_counts_for_filing(db, filing_id)
    
    print(f"[DEBUG] Vote removed - type: {vote_type}, new counts: {updated_counts}")
    
    return {
        "message": "Vote removed successfully",
        "vote_counts": updated_counts
    }


@router.get("/user/votes")
async def get_user_votes(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get all votes by the current user
    """
    # Get user's votes with filing information
    votes = db.query(UserVote).filter(
        UserVote.user_id == current_user.id
    ).order_by(desc(UserVote.created_at)).offset(skip).limit(limit).all()
    
    # Get total count
    total = db.query(func.count(UserVote.id)).filter(
        UserVote.user_id == current_user.id
    ).scalar()
    
    # Format response
    result = []
    for vote in votes:
        filing = db.query(Filing).filter(Filing.id == vote.filing_id).first()
        if filing:
            result.append({
                "filing_id": vote.filing_id,
                "vote_type": vote.vote_type,
                "created_at": vote.created_at.isoformat() if vote.created_at else None,
                "filing": {
                    "ticker": filing.ticker,
                    "form_type": filing.filing_type.value if filing.filing_type else None,
                    "filing_date": filing.filing_date.isoformat() if filing.filing_date else None
                }
            })
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "votes": result
    }


@router.get("/filings/{filing_id}/vote-distribution")
async def get_vote_distribution(
    filing_id: int,
    db: Session = Depends(get_db)
):
    """
    Get vote distribution for a filing (public endpoint)
    """
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    # Get vote counts
    vote_counts = get_vote_counts_for_filing(db, filing_id)
    total = sum(vote_counts.values())
    
    # Calculate percentages
    distribution = {}
    for sentiment, count in vote_counts.items():
        percentage = (count / total * 100) if total > 0 else 0
        distribution[sentiment] = {
            "count": count,
            "percentage": round(percentage, 1)
        }
    
    return {
        "filing_id": filing_id,
        "total_votes": total,
        "distribution": distribution
    }
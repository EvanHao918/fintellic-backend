"""
Comments API endpoints
"""
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from app.api import deps
from app.models import User, Filing, Comment, CommentVote, UserTier
from app.schemas.comment import (
    CommentCreate,
    CommentUpdate,
    CommentResponse,
    CommentListResponse,
    CommentVoteRequest,
    CommentVoteResponse
)
from app.core.database import get_db

router = APIRouter()


@router.get("/filings/{filing_id}/comments", response_model=CommentListResponse)
async def get_filing_comments(
    filing_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(deps.get_current_user_optional)
):
    """
    Get comments for a specific filing
    Public endpoint - authentication optional
    """
    # Check if filing exists
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    # Get comments with user information
    comments_query = db.query(Comment).filter(
        Comment.filing_id == filing_id
    ).options(
        joinedload(Comment.user),
        joinedload(Comment.votes)
    ).order_by(desc(Comment.created_at))
    
    total = comments_query.count()
    comments = comments_query.offset(skip).limit(limit).all()
    
    # Build response
    items = []
    for comment in comments:
        # Get user vote if logged in
        user_vote = 0
        if current_user:
            user_vote = comment.get_user_vote(current_user.id)
        
        items.append(CommentResponse(
            id=comment.id,
            filing_id=comment.filing_id,
            user_id=comment.user_id,
            username=comment.user.username or comment.user.email.split('@')[0],
            user_tier=comment.user.tier,
            content=comment.content,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
            is_editable=comment.is_editable(current_user.id) if current_user else False,
            upvotes=comment.upvotes,
            downvotes=comment.downvotes,
            net_votes=comment.net_votes,
            user_vote=user_vote
        ))
    
    return CommentListResponse(total=total, items=items)


@router.post("/filings/{filing_id}/comments", response_model=CommentResponse)
async def create_comment(
    filing_id: int,
    comment_in: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Create a new comment on a filing
    Requires authentication
    """
    # Check if filing exists
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    # Create comment
    comment = Comment(
        filing_id=filing_id,
        user_id=current_user.id,
        content=comment_in.content
    )
    
    db.add(comment)
    
    # Update filing comment count
    filing.comment_count = (filing.comment_count or 0) + 1
    
    db.commit()
    db.refresh(comment)
    
    return CommentResponse(
        id=comment.id,
        filing_id=comment.filing_id,
        user_id=comment.user_id,
        username=current_user.username or current_user.email.split('@')[0],
        user_tier=current_user.tier,
        content=comment.content,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        is_editable=True,  # Just created, so editable
        upvotes=0,
        downvotes=0,
        net_votes=0,
        user_vote=0
    )


@router.post("/comments/{comment_id}/vote", response_model=CommentVoteResponse)
async def vote_comment(
    comment_id: int,
    vote_request: CommentVoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Vote on a comment (upvote, downvote, or remove vote)
    Requires authentication
    """
    # Get comment
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # Get existing vote
    existing_vote = db.query(CommentVote).filter(
        CommentVote.comment_id == comment_id,
        CommentVote.user_id == current_user.id
    ).first()
    
    # Map vote_type string to integer
    vote_map = {"upvote": 1, "downvote": -1, "none": 0}
    new_vote_value = vote_map[vote_request.vote_type]
    
    # Update vote counts
    if existing_vote:
        # Remove old vote from counts
        if existing_vote.vote_type == 1:
            comment.upvotes = max(0, comment.upvotes - 1)
        elif existing_vote.vote_type == -1:
            comment.downvotes = max(0, comment.downvotes - 1)
        
        if new_vote_value == 0:
            # Remove vote
            db.delete(existing_vote)
        else:
            # Update vote
            existing_vote.vote_type = new_vote_value
            existing_vote.updated_at = datetime.now(timezone.utc)
    else:
        # Create new vote
        if new_vote_value != 0:
            vote = CommentVote(
                user_id=current_user.id,
                comment_id=comment_id,
                vote_type=new_vote_value
            )
            db.add(vote)
    
    # Add new vote to counts
    if new_vote_value == 1:
        comment.upvotes += 1
    elif new_vote_value == -1:
        comment.downvotes += 1
    
    db.commit()
    
    return CommentVoteResponse(
        comment_id=comment_id,
        upvotes=comment.upvotes,
        downvotes=comment.downvotes,
        net_votes=comment.net_votes,
        user_vote=new_vote_value
    )


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Delete a comment
    Only the author can delete their comment
    """
    # Get comment
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # Check permissions
    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own comments"
        )
    
    # Update filing comment count
    filing = db.query(Filing).filter(Filing.id == comment.filing_id).first()
    if filing:
        filing.comment_count = max(0, (filing.comment_count or 0) - 1)
    
    # Delete comment (votes will cascade delete)
    db.delete(comment)
    db.commit()
    
    return {"status": "success", "message": "Comment deleted"}
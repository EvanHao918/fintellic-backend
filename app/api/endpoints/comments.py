"""
Comments API endpoints
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from app.api import deps
from app.models import User, Filing, Comment, UserTier
from app.schemas.comment import (
    CommentCreate,
    CommentUpdate,
    CommentResponse,
    CommentListResponse
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
        joinedload(Comment.user)
    ).order_by(desc(Comment.created_at))
    
    total = comments_query.count()
    comments = comments_query.offset(skip).limit(limit).all()
    
    return CommentListResponse(
        total=total,
        items=[
            CommentResponse(
                id=comment.id,
                filing_id=comment.filing_id,
                user_id=comment.user_id,
                username=comment.user.username or comment.user.email.split('@')[0],
                user_tier=comment.user.tier,
                content=comment.content,
                created_at=comment.created_at,
                updated_at=comment.updated_at,
                is_editable=comment.is_editable(current_user.id) if current_user else False
            )
            for comment in comments
        ]
    )


@router.post("/filings/{filing_id}/comments", response_model=CommentResponse)
async def create_comment(
    filing_id: int,
    comment_data: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Create a new comment on a filing
    Requires authentication and Pro tier
    """
    # Check user tier
    if current_user.tier != UserTier.PRO:
        raise HTTPException(
            status_code=403, 
            detail="Comments are available for Pro users only"
        )
    
    # Check if filing exists
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    
    # Create comment
    comment = Comment(
        filing_id=filing_id,
        user_id=current_user.id,
        content=comment_data.content
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
        is_editable=True  # Just created, so editable
    )


@router.put("/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: int,
    comment_update: CommentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Update a comment
    Only the author can update within 5 minutes of creation
    """
    # Get comment
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # Check if user can edit
    if not comment.is_editable(current_user.id):
        raise HTTPException(
            status_code=403, 
            detail="You can only edit your own comments within 5 minutes of posting"
        )
    
    # Update comment
    comment.content = comment_update.content
    comment.updated_at = datetime.utcnow()
    
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
        is_editable=True
    )


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Delete a comment
    Only the author can delete their own comments
    """
    # Get comment
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # Check if user owns the comment
    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=403, 
            detail="You can only delete your own comments"
        )
    
    # Update filing comment count
    filing = db.query(Filing).filter(Filing.id == comment.filing_id).first()
    if filing:
        filing.comment_count = max(0, (filing.comment_count or 0) - 1)
    
    # Delete comment
    db.delete(comment)
    db.commit()
    
    return {"message": "Comment deleted successfully"}
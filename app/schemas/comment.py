"""
Comment schemas for request/response validation
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from app.models import UserTier


class CommentBase(BaseModel):
    """Base comment schema"""
    content: str = Field(..., min_length=1, max_length=1000)


class CommentCreate(CommentBase):
    """Schema for creating a comment"""
    pass


class CommentUpdate(BaseModel):
    """Schema for updating a comment"""
    content: str = Field(..., min_length=1, max_length=1000)


class CommentVoteRequest(BaseModel):
    """Schema for voting on a comment"""
    vote_type: str = Field(..., pattern="^(upvote|downvote|none)$")


class CommentResponse(BaseModel):
    """Schema for comment response"""
    id: int
    filing_id: int
    user_id: int
    username: str
    user_tier: UserTier
    content: str
    created_at: datetime
    updated_at: Optional[datetime]
    is_editable: bool = False
    upvotes: int = 0
    downvotes: int = 0
    net_votes: int = 0
    user_vote: int = 0  # -1, 0, or 1
    
    class Config:
        from_attributes = True


class CommentListResponse(BaseModel):
    """Schema for paginated comment list"""
    total: int
    items: List[CommentResponse]


class CommentVoteResponse(BaseModel):
    """Schema for vote response"""
    comment_id: int
    upvotes: int
    downvotes: int
    net_votes: int
    user_vote: int
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


class CommentUpdate(CommentBase):
    """Schema for updating a comment"""
    pass


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
    
    class Config:
        from_attributes = True


class CommentListResponse(BaseModel):
    """Schema for paginated comment list"""
    total: int
    items: List[CommentResponse]
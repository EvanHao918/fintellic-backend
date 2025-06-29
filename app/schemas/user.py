from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, validator
from app.models.user import UserTier


# Base schemas
class UserBase(BaseModel):
    """Base user schema with common attributes"""
    email: EmailStr
    full_name: Optional[str] = None
    username: Optional[str] = None
    is_active: bool = True


# Request schemas
class UserCreate(UserBase):
    """Schema for creating a new user"""
    password: str = Field(..., min_length=8, max_length=100)
    
    @validator('password')
    def validate_password(cls, v):
        """Ensure password meets security requirements"""
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(char.islower() for char in v):
            raise ValueError('Password must contain at least one lowercase letter')
        return v


class UserUpdate(BaseModel):
    """Schema for updating user profile"""
    full_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[EmailStr] = None


class UserUpdatePassword(BaseModel):
    """Schema for changing password"""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
    
    @validator('new_password')
    def validate_password(cls, v, values):
        """Ensure new password meets requirements and is different from current"""
        if 'current_password' in values and v == values['current_password']:
            raise ValueError('New password must be different from current password')
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(char.islower() for char in v):
            raise ValueError('Password must contain at least one lowercase letter')
        return v


# Response schemas
class UserResponse(UserBase):
    """Schema for user response"""
    id: int
    tier: UserTier
    created_at: datetime
    last_login_at: Optional[datetime] = None
    is_verified: bool
    daily_reports_count: int = 0
    subscription_expires_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True
        from_attributes = True


class UserPublic(BaseModel):
    """Public user information (for comments, etc.)"""
    id: int
    username: Optional[str] = None
    tier: UserTier
    
    class Config:
        orm_mode = True
        from_attributes = True


class UserInDB(UserBase):
    """User schema with hashed password (internal use)"""
    id: int
    hashed_password: str
    tier: UserTier
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True
        from_attributes = True
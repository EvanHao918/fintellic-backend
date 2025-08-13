from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, EmailStr, Field, validator

# Note: These enums should match the database enums
# Database enums are uppercase: FREE, PRO, MONTHLY, YEARLY, EARLY_BIRD, STANDARD
class UserTier(str):
    FREE = "FREE"
    PRO = "PRO"

class SubscriptionType(str):
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"

class PricingTier(str):
    EARLY_BIRD = "EARLY_BIRD"
    STANDARD = "STANDARD"


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
    promo_code: Optional[str] = None  # 注册时可以使用优惠码
    referral_code: Optional[str] = None  # 推荐码
    registration_source: Optional[str] = "email"  # email, google, apple
    registration_device_type: Optional[str] = "web"  # web, ios, android
    
    # Social login IDs
    google_user_id: Optional[str] = None
    apple_user_id: Optional[str] = None
    
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


# Subscription related schemas
class SubscriptionInfo(BaseModel):
    """用户订阅信息"""
    is_active: bool
    subscription_type: Optional[str] = None
    pricing_tier: Optional[str] = None
    status: str  # active, cancelled, expired, inactive
    monthly_price: float
    current_price: Optional[float] = None
    expires_at: Optional[datetime] = None
    next_billing_date: Optional[datetime] = None
    auto_renew: bool = True
    payment_method: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    days_remaining: Optional[int] = None
    
    # Subscription history
    started_at: Optional[datetime] = None
    total_payments: float = 0
    last_payment_date: Optional[datetime] = None
    last_payment_amount: Optional[float] = None
    
    class Config:
        from_attributes = True


class PricingInfo(BaseModel):
    """价格信息（用于前端显示）"""
    is_early_bird: bool
    user_sequence_number: Optional[int] = None
    pricing_tier: str
    monthly_price: float
    yearly_price: float
    yearly_savings: float
    yearly_savings_percentage: int = 40
    early_bird_slots_remaining: Optional[int] = None
    currency: str = "USD"
    
    # Features
    features: Dict[str, bool] = Field(default_factory=lambda: {
        "unlimited_reports": True,
        "ai_analysis": True,
        "push_notifications": True,
        "priority_support": False,
        "early_access": False
    })
    
    class Config:
        from_attributes = True


# Response schemas
class UserResponse(UserBase):
    """Schema for user response"""
    id: int
    tier: str  # FREE or PRO
    created_at: datetime
    last_login_at: Optional[datetime] = None
    is_verified: bool
    daily_reports_count: int = 0
    subscription_expires_at: Optional[datetime] = None
    
    # 新增订阅相关字段
    subscription_type: Optional[str] = None
    pricing_tier: Optional[str] = None
    is_subscription_active: bool = False
    is_early_bird: bool = False
    subscription_status: str = "inactive"
    monthly_price: float = 49.00
    yearly_price: float = 352.80
    next_billing_date: Optional[datetime] = None
    subscription_auto_renew: bool = True
    
    class Config:
        orm_mode = True
        from_attributes = True


class UserDetailResponse(UserResponse):
    """详细的用户响应（包含更多订阅信息）"""
    user_sequence_number: Optional[int] = None
    subscription_started_at: Optional[datetime] = None
    subscription_cancelled_at: Optional[datetime] = None
    subscription_price: Optional[float] = None
    last_payment_date: Optional[datetime] = None
    last_payment_amount: Optional[float] = None
    total_payment_amount: float = 0
    promo_code_used: Optional[str] = None
    discount_percentage: Optional[int] = None
    referral_code: Optional[str] = None
    subscription_metadata: Optional[Dict[str, Any]] = None
    
    # Additional subscription details
    stripe_subscription_id: Optional[str] = None
    apple_subscription_id: Optional[str] = None
    google_subscription_id: Optional[str] = None
    
    class Config:
        orm_mode = True
        from_attributes = True


class UserPublic(BaseModel):
    """Public user information (for comments, etc.)"""
    id: int
    username: Optional[str] = None
    tier: str
    is_early_bird: bool = False  # 显示早鸟标识
    
    class Config:
        orm_mode = True
        from_attributes = True


class UserInDB(UserBase):
    """User schema with hashed password (internal use)"""
    id: int
    hashed_password: str
    tier: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Subscription fields
    is_early_bird: bool = False
    pricing_tier: Optional[str] = None
    user_sequence_number: Optional[int] = None
    is_subscription_active: bool = False
    subscription_type: Optional[str] = None
    subscription_expires_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True
        from_attributes = True
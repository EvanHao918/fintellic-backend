from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, validator
from enum import Enum


# Enums (matching database)
class SubscriptionType(str, Enum):
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class PricingTier(str, Enum):
    EARLY_BIRD = "EARLY_BIRD"
    STANDARD = "STANDARD"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PENDING = "pending"


class PaymentMethod(str, Enum):
    STRIPE = "stripe"
    APPLE = "apple"
    GOOGLE = "google"


# Request Schemas
class SubscriptionCreate(BaseModel):
    """创建订阅请求"""
    subscription_type: SubscriptionType
    payment_method: PaymentMethod
    promo_code: Optional[str] = None
    auto_renew: bool = True


class SubscriptionUpdate(BaseModel):
    """更新订阅（切换月付/年付）"""
    subscription_type: SubscriptionType
    immediate: bool = False  # 是否立即生效


class SubscriptionCancel(BaseModel):
    """取消订阅请求"""
    reason: Optional[str] = None
    feedback: Optional[str] = None
    cancel_immediately: bool = False  # 是否立即取消（不等到期）


# Response Schemas
class PricingInfo(BaseModel):
    """价格信息（用于前端显示）"""
    is_early_bird: bool
    user_sequence_number: Optional[int] = None
    pricing_tier: PricingTier
    monthly_price: float
    yearly_price: float
    yearly_savings: float
    yearly_savings_percentage: int = 40
    early_bird_slots_remaining: Optional[int] = None
    currency: str = "USD"
    
    # Features
    features: Dict[str, bool] = {
        "unlimited_reports": True,
        "ai_analysis": True,
        "push_notifications": True,
        "priority_support": False,
        "early_access": False
    }
    
    class Config:
        from_attributes = True


class SubscriptionInfo(BaseModel):
    """当前订阅信息"""
    is_active: bool
    subscription_type: Optional[SubscriptionType] = None
    pricing_tier: Optional[PricingTier] = None
    status: SubscriptionStatus
    monthly_price: float
    current_price: Optional[float] = None  # 当前支付的价格
    expires_at: Optional[datetime] = None
    next_billing_date: Optional[datetime] = None
    auto_renew: bool = True
    payment_method: Optional[PaymentMethod] = None
    cancelled_at: Optional[datetime] = None
    days_remaining: Optional[int] = None
    
    # Subscription history
    started_at: Optional[datetime] = None
    total_payments: float = 0
    last_payment_date: Optional[datetime] = None
    last_payment_amount: Optional[float] = None
    
    class Config:
        from_attributes = True


class SubscriptionResponse(BaseModel):
    """订阅操作响应"""
    success: bool
    message: str
    subscription_info: Optional[SubscriptionInfo] = None
    payment_required: bool = False
    payment_url: Optional[str] = None  # Stripe checkout URL等
    client_secret: Optional[str] = None  # Stripe payment intent secret
    
    class Config:
        from_attributes = True


class PaymentHistory(BaseModel):
    """支付历史记录"""
    id: int
    amount: float
    currency: str = "USD"
    payment_method: PaymentMethod
    payment_status: str
    transaction_id: Optional[str] = None
    created_at: datetime
    description: Optional[str] = None
    
    class Config:
        from_attributes = True


class SubscriptionHistory(BaseModel):
    """订阅历史记录"""
    id: int
    subscription_type: SubscriptionType
    pricing_tier: PricingTier
    price: float
    started_at: datetime
    expires_at: datetime
    status: SubscriptionStatus
    cancelled_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class CreateCheckoutSession(BaseModel):
    """创建Stripe Checkout Session请求"""
    subscription_type: SubscriptionType
    success_url: str
    cancel_url: str
    promo_code: Optional[str] = None


class CheckoutSessionResponse(BaseModel):
    """Stripe Checkout Session响应"""
    session_id: str
    checkout_url: str
    publishable_key: str


class SubscriptionStatistics(BaseModel):
    """订阅统计信息（管理员用）"""
    total_subscribers: int
    active_subscribers: int
    monthly_subscribers: int
    yearly_subscribers: int
    early_bird_subscribers: int
    standard_subscribers: int
    total_revenue: float
    monthly_revenue: float
    churn_rate: float
    average_lifetime_value: float
    
    class Config:
        from_attributes = True


class EarlyBirdStatus(BaseModel):
    """早鸟状态信息"""
    early_bird_limit: int = 10000
    early_bird_users: int
    slots_remaining: int
    is_available: bool
    percentage_used: float
    
    # Pricing info
    early_bird_monthly_price: float = 39.00
    early_bird_yearly_price: float = 280.80
    standard_monthly_price: float = 49.00
    standard_yearly_price: float = 352.80
    
    # Marketing message
    marketing_message: Optional[str] = None
    urgency_level: Optional[str] = None  # low, medium, high, critical
    
    class Config:
        from_attributes = True


class PromoCode(BaseModel):
    """优惠码信息"""
    code: str
    discount_percentage: Optional[int] = None
    discount_amount: Optional[float] = None
    valid_until: Optional[datetime] = None
    usage_limit: Optional[int] = None
    usage_count: int = 0
    is_active: bool = True
    applicable_plans: List[str] = []  # plan_names that this code applies to
    
    class Config:
        from_attributes = True
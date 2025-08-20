from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Date, Numeric, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.models.base import Base


class UserTier(str, enum.Enum):
    FREE = "FREE"  # 数据库中是大写
    PRO = "PRO"    # 数据库中是大写
    

class SubscriptionType(str, enum.Enum):
    """订阅类型枚举"""
    MONTHLY = "MONTHLY"  # 保持大写一致性
    YEARLY = "YEARLY"    # 保持大写一致性
    

class PricingTier(str, enum.Enum):
    """价格层级枚举"""
    EARLY_BIRD = "EARLY_BIRD"  # 保持大写一致性
    STANDARD = "STANDARD"      # 保持大写一致性
    
    
class User(Base):
    __tablename__ = "users"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Authentication fields
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Nullable for social auth
    
    # User information
    full_name = Column(String(255))
    username = Column(String(50), unique=True, index=True)
    avatar_url = Column(String(512))  # For social auth profile pictures
    
    # Social authentication IDs
    apple_user_id = Column(String(255), unique=True, index=True, nullable=True)
    google_user_id = Column(String(255), unique=True, index=True, nullable=True)
    linkedin_user_id = Column(String(255), unique=True, index=True, nullable=True)
    
    # Subscription status
    tier = Column(Enum(UserTier), default=UserTier.FREE, nullable=False)
    subscription_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # ============ 订阅管理字段 ============
    # 订阅相关
    subscription_type = Column(Enum(SubscriptionType), nullable=True)  # monthly/yearly
    pricing_tier = Column(Enum(PricingTier), nullable=True)  # early_bird/standard
    subscription_started_at = Column(DateTime(timezone=True), nullable=True)  # 订阅开始时间
    subscription_cancelled_at = Column(DateTime(timezone=True), nullable=True)  # 取消时间
    subscription_price = Column(Numeric(10, 2), nullable=True)  # 锁定的订阅价格
    
    # 支付相关
    stripe_customer_id = Column(String(255), nullable=True, index=True)  # Stripe客户ID
    stripe_subscription_id = Column(String(255), nullable=True)  # Stripe订阅ID
    apple_subscription_id = Column(String(255), nullable=True)  # Apple订阅ID
    google_subscription_id = Column(String(255), nullable=True)  # Google订阅ID
    
    # 订阅历史和状态
    is_subscription_active = Column(Boolean, default=False)  # 订阅是否活跃
    subscription_auto_renew = Column(Boolean, default=True)  # 是否自动续费
    next_billing_date = Column(DateTime(timezone=True), nullable=True)  # 下次扣费日期
    last_payment_date = Column(DateTime(timezone=True), nullable=True)  # 最后支付日期
    last_payment_amount = Column(Numeric(10, 2), nullable=True)  # 最后支付金额
    total_payment_amount = Column(Numeric(10, 2), default=0)  # 总支付金额
    
    # 早鸟用户标记
    is_early_bird = Column(Boolean, default=False)  # 是否是早鸟用户
    early_bird_registered_at = Column(DateTime(timezone=True), nullable=True)  # 早鸟注册时间
    user_sequence_number = Column(Integer, nullable=True, index=True)  # 用户序号（用于判断前10000名）
    
    # 优惠和促销
    promo_code_used = Column(String(50), nullable=True)  # 使用的优惠码
    discount_percentage = Column(Integer, nullable=True)  # 折扣百分比
    referral_code = Column(String(50), unique=True, nullable=True)  # 推荐码
    referred_by_user_id = Column(Integer, nullable=True)  # 推荐人ID
    
    # 订阅元数据（JSON格式，存储额外信息）
    subscription_metadata = Column(JSON, nullable=True)  # 可存储支付方式、账单地址等
    # ============ 结束订阅字段 ============
    
    # Account status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True))
    last_login_ip = Column(String(45))
    
    # Registration tracking
    registration_source = Column(String(50))  # email, apple, google, linkedin
    registration_device_type = Column(String(50))  # ios, android, web
    
    # Biometric settings (stored as JSON)
    biometric_settings = Column(String(512))  # {"face_id": true, "devices": [...]}
    
    # Device tokens for push notifications (Phase 4)
    device_tokens = Column(String(2048))  # JSON array of device tokens
    
    # Daily limits for free users
    daily_reports_count = Column(Integer, default=0)
    daily_reports_reset_at = Column(DateTime(timezone=True))
    
    # Daily view tracking
    last_view_date = Column(Date, nullable=True)
    daily_view_count = Column(Integer, nullable=True, default=0)
    
    # Relationships
    comments = relationship("Comment", back_populates="user", cascade="all, delete-orphan", foreign_keys="Comment.user_id")
    votes = relationship("UserVote", back_populates="user", cascade="all, delete-orphan")
    watchlist = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    filing_views = relationship("UserFilingView", back_populates="user", cascade="all, delete-orphan")
    comment_votes = relationship("CommentVote", back_populates="user", cascade="all, delete-orphan")
    
    # Phase 2关系 - 订阅
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan", foreign_keys="[Subscription.user_id]")
    payment_records = relationship("PaymentRecord", back_populates="user", cascade="all, delete-orphan", foreign_keys="[PaymentRecord.user_id]")
    
    # Phase 4关系 - 通知设置（新增）
    notification_settings = relationship(
        "UserNotificationSettings", 
        back_populates="user", 
        uselist=False,  # 一对一关系
        cascade="all, delete-orphan"
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', tier={self.tier}, pricing_tier={self.pricing_tier})>"
    
    @property
    def is_pro(self):
        """Check if user is a pro subscriber"""
        return self.tier == UserTier.PRO and self.is_subscription_active
    
    @property
    def has_social_auth(self):
        """Check if user has any social authentication"""
        return bool(self.apple_user_id or self.google_user_id or self.linkedin_user_id)
    
    @property
    def subscription_status(self):
        """Get detailed subscription status"""
        if not self.is_subscription_active:
            return "inactive"
        elif self.subscription_cancelled_at:
            return "cancelled_pending"  # 已取消但还未到期
        else:
            return "active"
    
    @property
    def monthly_price(self):
        """Get user's monthly price based on pricing tier"""
        if self.pricing_tier == PricingTier.EARLY_BIRD:
            return 39.00
        else:
            return 49.00
    
    @property
    def yearly_price(self):
        """Get user's yearly price (60% of monthly * 12)"""
        return self.monthly_price * 12 * 0.6
    
    @property
    def has_device_tokens(self):
        """Check if user has registered device tokens for notifications"""
        if not self.device_tokens:
            return False
        try:
            import json
            tokens = json.loads(self.device_tokens)
            return len(tokens) > 0
        except:
            return False
    
    def get_device_tokens(self):
        """Get list of device tokens"""
        if not self.device_tokens:
            return []
        try:
            import json
            tokens = json.loads(self.device_tokens)
            return [t.get('token') for t in tokens if t.get('token')]
        except:
            return []
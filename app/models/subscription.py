from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.models.base import Base


class SubscriptionStatus(str, enum.Enum):
    """订阅状态枚举"""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PENDING = "pending"


class PaymentMethod(str, enum.Enum):
    """支付方式枚举"""
    STRIPE = "stripe"
    APPLE = "apple"
    GOOGLE = "google"
    

class Subscription(Base):
    """订阅历史表"""
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # 订阅信息
    subscription_type = Column(String(20), nullable=False)  # MONTHLY/YEARLY
    pricing_tier = Column(String(20), nullable=False)  # EARLY_BIRD/STANDARD
    price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")
    status = Column(String(50), nullable=False)  # active, cancelled, expired, pending
    
    # 时间信息
    started_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    
    # 续费设置
    auto_renew = Column(Boolean, default=True)
    
    # 支付信息
    payment_method = Column(String(50))
    stripe_subscription_id = Column(String(255))
    apple_subscription_id = Column(String(255))
    google_subscription_id = Column(String(255))
    
    # 元数据（改名避免与SQLAlchemy保留字冲突）
    subscription_metadata = Column(JSON)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    user = relationship("User", back_populates="subscriptions")
    payment_records = relationship("PaymentRecord", back_populates="subscription")
    
    def __repr__(self):
        return f"<Subscription(id={self.id}, user_id={self.user_id}, status={self.status})>"
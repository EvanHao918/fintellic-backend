from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.models.base import Base


class PaymentStatus(str, enum.Enum):
    """支付状态枚举"""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    REFUNDED = "refunded"


class PaymentRecord(Base):
    """支付记录表"""
    __tablename__ = "payment_records"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    
    # 支付金额
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")
    
    # 支付信息
    payment_method = Column(String(50), nullable=False)
    payment_status = Column(String(50), nullable=False)  # success, failed, pending, refunded
    transaction_id = Column(String(255), unique=True)
    
    # 第三方支付ID
    stripe_payment_intent_id = Column(String(255))
    apple_transaction_id = Column(String(255))
    google_order_id = Column(String(255))
    
    # 失败和退款信息
    failure_reason = Column(Text)
    refund_amount = Column(Numeric(10, 2))
    refunded_at = Column(DateTime(timezone=True))
    
    # 元数据（改名避免与SQLAlchemy保留字冲突）
    payment_metadata = Column(JSON)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    user = relationship("User", back_populates="payment_records")
    subscription = relationship("Subscription", back_populates="payment_records")
    
    def __repr__(self):
        return f"<PaymentRecord(id={self.id}, user_id={self.user_id}, amount={self.amount}, status={self.payment_status})>"
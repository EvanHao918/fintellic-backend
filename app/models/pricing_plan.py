from sqlalchemy import Column, Integer, String, Boolean, DateTime, Numeric, JSON
from sqlalchemy.sql import func
from app.models.base import Base


class PricingPlan(Base):
    """价格计划表"""
    __tablename__ = "pricing_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    plan_name = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    
    # 价格信息
    pricing_tier = Column(String(20), nullable=False)  # EARLY_BIRD/STANDARD
    billing_period = Column(String(20), nullable=False)  # monthly/yearly
    price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")
    
    # 功能列表
    features = Column(JSON)
    
    # 状态和排序
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<PricingPlan(id={self.id}, plan_name={self.plan_name}, price={self.price})>"
    
    @property
    def monthly_equivalent(self):
        """获取月均价格"""
        if self.billing_period == "yearly":
            return self.price / 12
        return self.price
    
    @property
    def savings_percentage(self):
        """获取节省百分比"""
        if self.billing_period == "yearly":
            return 40  # 固定40%折扣
        return 0
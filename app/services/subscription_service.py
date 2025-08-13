from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from fastapi import HTTPException, status

from app.core.config import settings
from app.models.user import User, UserTier, PricingTier, SubscriptionType
from app.models.subscription import Subscription
from app.models.payment_record import PaymentRecord
from app.models.pricing_plan import PricingPlan
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionUpdate,
    SubscriptionCancel,
    SubscriptionInfo,
    PricingInfo,
    SubscriptionResponse,
    EarlyBirdStatus,
    PaymentHistory,
    SubscriptionHistory
)


class SubscriptionService:
    """订阅服务类"""
    
    @staticmethod
    def get_user_pricing(db: Session, user: User) -> PricingInfo:
        """获取用户的价格信息"""
        try:
            # 获取早鸟统计
            early_bird_count = db.query(func.count(User.id)).filter(
                User.is_early_bird == True
            ).scalar() or 0
            
            slots_remaining = max(0, settings.EARLY_BIRD_LIMIT - early_bird_count)
            
            # 确定用户的价格
            if user.is_early_bird or user.pricing_tier == PricingTier.EARLY_BIRD:
                monthly_price = settings.EARLY_BIRD_MONTHLY_PRICE
                yearly_price = settings.EARLY_BIRD_YEARLY_PRICE
                pricing_tier = PricingTier.EARLY_BIRD
            else:
                monthly_price = settings.STANDARD_MONTHLY_PRICE
                yearly_price = settings.STANDARD_YEARLY_PRICE
                pricing_tier = PricingTier.STANDARD
            
            yearly_savings = (monthly_price * 12) - yearly_price
            
            return PricingInfo(
                is_early_bird=user.is_early_bird,
                user_sequence_number=user.user_sequence_number,
                pricing_tier=pricing_tier,
                monthly_price=monthly_price,
                yearly_price=yearly_price,
                yearly_savings=yearly_savings,
                yearly_savings_percentage=40,
                early_bird_slots_remaining=slots_remaining if not user.is_early_bird else None,
                features={
                    "unlimited_reports": True,
                    "ai_analysis": True,
                    "push_notifications": True,
                    "priority_support": pricing_tier == PricingTier.EARLY_BIRD,
                    "early_access": pricing_tier == PricingTier.EARLY_BIRD
                }
            )
        except Exception as e:
            print(f"Error in get_user_pricing: {str(e)}")
            raise
    
    @staticmethod
    def get_current_subscription(db: Session, user: User) -> SubscriptionInfo:
        """获取用户当前订阅信息"""
        try:
            # 先尝试从用户表获取订阅信息（避免直接查询 subscriptions 表）
            if not user.is_subscription_active:
                # 用户没有活跃订阅，返回默认信息
                return SubscriptionInfo(
                    is_active=False,
                    status="pending",
                    monthly_price=user.monthly_price or settings.STANDARD_MONTHLY_PRICE,
                    auto_renew=False,
                    total_payments=float(user.total_payment_amount or 0)
                )
            
            # 如果用户有活跃订阅，从用户表读取信息
            days_remaining = None
            if user.subscription_expires_at:
                days_remaining = max(0, (user.subscription_expires_at - datetime.now()).days)
            
            return SubscriptionInfo(
                is_active=True,
                subscription_type=user.subscription_type or SubscriptionType.MONTHLY,
                pricing_tier=user.pricing_tier or PricingTier.STANDARD,
                status="active",
                monthly_price=user.monthly_price or settings.STANDARD_MONTHLY_PRICE,
                current_price=float(user.subscription_price or user.monthly_price or settings.STANDARD_MONTHLY_PRICE),
                expires_at=user.subscription_expires_at,
                next_billing_date=user.next_billing_date,
                auto_renew=user.subscription_auto_renew if hasattr(user, 'subscription_auto_renew') else True,
                payment_method=user.payment_method if hasattr(user, 'payment_method') else None,
                cancelled_at=user.subscription_cancelled_at,
                days_remaining=days_remaining,
                started_at=user.subscription_started_at,
                total_payments=float(user.total_payment_amount or 0),
                last_payment_date=user.last_payment_date,
                last_payment_amount=float(user.last_payment_amount) if user.last_payment_amount else None
            )
            
        except Exception as e:
            print(f"Error in get_current_subscription: {str(e)}")
            # 如果查询失败，返回基本信息
            return SubscriptionInfo(
                is_active=user.tier == UserTier.PRO,
                status="active" if user.tier == UserTier.PRO else "pending",
                monthly_price=user.monthly_price or settings.STANDARD_MONTHLY_PRICE,
                auto_renew=False,
                total_payments=0
            )
    
    @staticmethod
    def create_subscription(
        db: Session, 
        user: User, 
        subscription_data: SubscriptionCreate
    ) -> SubscriptionResponse:
        """创建新订阅（模拟）"""
        try:
            # 检查是否已有活跃订阅
            if user.is_subscription_active:
                return SubscriptionResponse(
                    success=False,
                    message="You already have an active subscription",
                    subscription_info=SubscriptionService.get_current_subscription(db, user)
                )
            
            # 确定价格
            pricing_info = SubscriptionService.get_user_pricing(db, user)
            
            if subscription_data.subscription_type == SubscriptionType.MONTHLY:
                price = pricing_info.monthly_price
                expires_at = datetime.now() + timedelta(days=30)
            else:  # YEARLY
                price = pricing_info.yearly_price
                expires_at = datetime.now() + timedelta(days=365)
            
            # 在 Phase 2，我们直接更新用户表（不创建 Subscription 记录）
            user.tier = UserTier.PRO
            user.is_subscription_active = True
            user.subscription_type = subscription_data.subscription_type
            user.subscription_started_at = datetime.now()
            user.subscription_expires_at = expires_at
            user.next_billing_date = expires_at
            user.subscription_price = price
            user.subscription_auto_renew = subscription_data.auto_renew
            user.payment_method = subscription_data.payment_method.value if subscription_data.payment_method else None
            user.last_payment_date = datetime.now()
            user.last_payment_amount = price
            user.total_payment_amount = (user.total_payment_amount or 0) + price
            
            db.commit()
            
            return SubscriptionResponse(
                success=True,
                message="Subscription created successfully (mock)",
                subscription_info=SubscriptionService.get_current_subscription(db, user)
            )
            
        except Exception as e:
            print(f"Error in create_subscription: {str(e)}")
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create subscription: {str(e)}"
            )
    
    @staticmethod
    def update_subscription(
        db: Session,
        user: User,
        update_data: SubscriptionUpdate
    ) -> SubscriptionResponse:
        """更新订阅（切换月付/年付）"""
        try:
            if not user.is_subscription_active:
                return SubscriptionResponse(
                    success=False,
                    message="No active subscription found",
                    subscription_info=None
                )
            
            # 如果类型相同，无需更新
            if user.subscription_type == update_data.subscription_type:
                return SubscriptionResponse(
                    success=False,
                    message="You are already on this plan",
                    subscription_info=SubscriptionService.get_current_subscription(db, user)
                )
            
            # 计算新价格和到期时间
            pricing_info = SubscriptionService.get_user_pricing(db, user)
            
            if update_data.subscription_type == SubscriptionType.MONTHLY:
                new_price = pricing_info.monthly_price
                new_expires_at = datetime.now() + timedelta(days=30)
            else:  # YEARLY
                new_price = pricing_info.yearly_price
                new_expires_at = datetime.now() + timedelta(days=365)
            
            # 更新用户
            user.subscription_type = update_data.subscription_type
            user.subscription_price = new_price
            if update_data.immediate:
                user.subscription_expires_at = new_expires_at
                user.next_billing_date = new_expires_at
            
            db.commit()
            
            return SubscriptionResponse(
                success=True,
                message=f"Subscription updated to {update_data.subscription_type.value}",
                subscription_info=SubscriptionService.get_current_subscription(db, user)
            )
            
        except Exception as e:
            print(f"Error in update_subscription: {str(e)}")
            db.rollback()
            raise
    
    @staticmethod
    def cancel_subscription(
        db: Session,
        user: User,
        cancel_data: SubscriptionCancel
    ) -> SubscriptionResponse:
        """取消订阅"""
        try:
            if not user.is_subscription_active:
                return SubscriptionResponse(
                    success=False,
                    message="No active subscription found",
                    subscription_info=None
                )
            
            user.subscription_cancelled_at = datetime.now()
            user.subscription_auto_renew = False
            
            if cancel_data.cancel_immediately:
                # 立即取消
                user.tier = UserTier.FREE
                user.is_subscription_active = False
                user.subscription_expires_at = datetime.now()
                message = "Subscription cancelled immediately"
            else:
                # 到期后取消
                message = f"Subscription will be cancelled on {user.subscription_expires_at.date()}"
            
            db.commit()
            
            return SubscriptionResponse(
                success=True,
                message=message,
                subscription_info=SubscriptionService.get_current_subscription(db, user)
            )
            
        except Exception as e:
            print(f"Error in cancel_subscription: {str(e)}")
            db.rollback()
            raise
    
    @staticmethod
    def get_payment_history(
        db: Session,
        user: User,
        limit: int = 10
    ) -> List[PaymentHistory]:
        """获取支付历史（从用户表模拟）"""
        # Phase 2: 返回模拟数据
        history = []
        if user.last_payment_date and user.last_payment_amount:
            history.append(
                PaymentHistory(
                    id=1,
                    amount=float(user.last_payment_amount),
                    currency="USD",
                    payment_method=user.payment_method or "card",
                    payment_status="success",
                    transaction_id=f"mock_{user.id}_{int(user.last_payment_date.timestamp())}",
                    created_at=user.last_payment_date,
                    description="Subscription payment"
                )
            )
        return history
    
    @staticmethod
    def get_subscription_history(
        db: Session,
        user: User
    ) -> List[SubscriptionHistory]:
        """获取订阅历史（从用户表模拟）"""
        # Phase 2: 返回模拟数据
        history = []
        if user.subscription_started_at:
            history.append(
                SubscriptionHistory(
                    id=1,
                    subscription_type=user.subscription_type.value if user.subscription_type else "MONTHLY",
                    pricing_tier=user.pricing_tier.value if user.pricing_tier else "STANDARD",
                    price=float(user.subscription_price or user.monthly_price or 49),
                    started_at=user.subscription_started_at,
                    expires_at=user.subscription_expires_at,
                    status="active" if user.is_subscription_active else "expired",
                    cancelled_at=user.subscription_cancelled_at
                )
            )
        return history
    
    @staticmethod
    def get_early_bird_status(db: Session) -> EarlyBirdStatus:
        """获取早鸟状态"""
        try:
            early_bird_count = db.query(func.count(User.id)).filter(
                User.is_early_bird == True
            ).scalar() or 0
            
            slots_remaining = max(0, settings.EARLY_BIRD_LIMIT - early_bird_count)
            percentage_used = (early_bird_count / settings.EARLY_BIRD_LIMIT) * 100 if settings.EARLY_BIRD_LIMIT > 0 else 0
            
            # 确定紧急程度
            if slots_remaining == 0:
                urgency_level = "sold_out"
                marketing_message = "Early bird offer SOLD OUT! Standard pricing now applies."
            elif slots_remaining < 100:
                urgency_level = "critical"
                marketing_message = f"🔥 LAST CHANCE! Only {slots_remaining} early bird spots left!"
            elif slots_remaining < 500:
                urgency_level = "high"
                marketing_message = f"⚡ HURRY! Only {slots_remaining} early bird spots remaining!"
            elif slots_remaining < 2000:
                urgency_level = "medium"
                marketing_message = f"🎯 Limited offer: {slots_remaining} early bird spots available"
            else:
                urgency_level = "low"
                marketing_message = f"🐦 Early bird special: Save $10/month forever!"
            
            return EarlyBirdStatus(
                early_bird_limit=settings.EARLY_BIRD_LIMIT,
                early_bird_users=early_bird_count,
                slots_remaining=slots_remaining,
                is_available=slots_remaining > 0,
                percentage_used=percentage_used,
                early_bird_monthly_price=settings.EARLY_BIRD_MONTHLY_PRICE,
                early_bird_yearly_price=settings.EARLY_BIRD_YEARLY_PRICE,
                standard_monthly_price=settings.STANDARD_MONTHLY_PRICE,
                standard_yearly_price=settings.STANDARD_YEARLY_PRICE,
                marketing_message=marketing_message,
                urgency_level=urgency_level
            )
        except Exception as e:
            print(f"Error in get_early_bird_status: {str(e)}")
            # 返回默认值
            return EarlyBirdStatus(
                early_bird_limit=10000,
                early_bird_users=0,
                slots_remaining=10000,
                is_available=True,
                percentage_used=0,
                early_bird_monthly_price=39,
                early_bird_yearly_price=280.80,
                standard_monthly_price=49,
                standard_yearly_price=352.80,
                marketing_message="Early bird special available!",
                urgency_level="low"
            )
    
    @staticmethod
    def get_subscription_statistics(db: Session) -> Dict[str, Any]:
        """获取订阅统计（管理员用）"""
        try:
            total_users = db.query(func.count(User.id)).scalar() or 0
            pro_users = db.query(func.count(User.id)).filter(
                User.tier == UserTier.PRO
            ).scalar() or 0
            early_bird_users = db.query(func.count(User.id)).filter(
                User.is_early_bird == True
            ).scalar() or 0
            
            return {
                "total_users": total_users,
                "pro_users": pro_users,
                "free_users": total_users - pro_users,
                "early_bird_users": early_bird_users,
                "conversion_rate": (pro_users / total_users * 100) if total_users > 0 else 0
            }
        except Exception as e:
            print(f"Error in get_subscription_statistics: {str(e)}")
            return {
                "total_users": 0,
                "pro_users": 0,
                "free_users": 0,
                "early_bird_users": 0,
                "conversion_rate": 0
            }


# 创建服务实例
subscription_service = SubscriptionService()
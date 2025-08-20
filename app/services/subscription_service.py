from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from fastapi import HTTPException, status
import logging

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

logger = logging.getLogger(__name__)


class SubscriptionService:
    """订阅服务类"""
    
    @staticmethod
    def _get_utc_now() -> datetime:
        """获取UTC时间，确保时区一致性"""
        return datetime.now(timezone.utc)
    
    @staticmethod
    def _ensure_utc_datetime(dt: Optional[datetime]) -> Optional[datetime]:
        """确保datetime是UTC时区感知的"""
        if dt is None:
            return None
        if dt.tzinfo is None:
            # 如果是naive datetime，假设为UTC
            return dt.replace(tzinfo=timezone.utc)
        return dt
    
    @staticmethod
    def _is_early_bird_by_sequence(user: User) -> bool:
        """基于序号判定是否为早鸟用户"""
        return user.user_sequence_number is not None and user.user_sequence_number <= settings.EARLY_BIRD_LIMIT
    
    @staticmethod
    def get_user_pricing(db: Session, user: User) -> PricingInfo:
        """获取用户的价格信息"""
        try:
            # 获取早鸟统计
            early_bird_count = db.query(func.count(User.id)).filter(
                User.user_sequence_number <= settings.EARLY_BIRD_LIMIT
            ).scalar() or 0
            
            slots_remaining = max(0, settings.EARLY_BIRD_LIMIT - early_bird_count)
            
            # 🔥 修复：基于序号判定早鸟状态，而非数据库字段
            is_early_bird = SubscriptionService._is_early_bird_by_sequence(user)
            
            # 确定用户的价格
            if is_early_bird:
                monthly_price = settings.EARLY_BIRD_MONTHLY_PRICE
                yearly_price = settings.EARLY_BIRD_YEARLY_PRICE
                pricing_tier = PricingTier.EARLY_BIRD
            else:
                monthly_price = settings.STANDARD_MONTHLY_PRICE
                yearly_price = settings.STANDARD_YEARLY_PRICE
                pricing_tier = PricingTier.STANDARD
            
            yearly_savings = (monthly_price * 12) - yearly_price
            
            # 🔥 修复：同时更新数据库中的早鸟状态，确保一致性
            if user.is_early_bird != is_early_bird:
                user.is_early_bird = is_early_bird
                user.pricing_tier = pricing_tier
                db.commit()
                logger.info(f"Updated early bird status for user {user.id}: sequence={user.user_sequence_number}, is_early_bird={is_early_bird}")
            
            return PricingInfo(
                is_early_bird=is_early_bird,
                user_sequence_number=user.user_sequence_number,
                pricing_tier=pricing_tier,
                monthly_price=monthly_price,
                yearly_price=yearly_price,
                yearly_savings=yearly_savings,
                yearly_savings_percentage=40,
                early_bird_slots_remaining=slots_remaining if not is_early_bird else None,
                features={
                    "unlimited_reports": True,
                    "ai_analysis": True,
                    "push_notifications": True,
                    "priority_support": pricing_tier == PricingTier.EARLY_BIRD,
                    "early_access": pricing_tier == PricingTier.EARLY_BIRD
                }
            )
        except Exception as e:
            logger.error(f"Error in get_user_pricing: {str(e)}")
            raise
    
    @staticmethod
    def get_current_subscription(db: Session, user: User) -> SubscriptionInfo:
        """获取用户当前订阅信息"""
        try:
            # 先尝试从用户表获取订阅信息
            if not user.is_subscription_active:
                # 用户没有活跃订阅，返回默认信息
                return SubscriptionInfo(
                    is_active=False,
                    status="pending",
                    monthly_price=user.monthly_price or settings.STANDARD_MONTHLY_PRICE,
                    auto_renew=False,
                    total_payments=float(user.total_payment_amount or 0)
                )
            
            # 🔥 修复：统一时区处理
            current_time = SubscriptionService._get_utc_now()
            expires_at = SubscriptionService._ensure_utc_datetime(user.subscription_expires_at)
            next_billing_date = SubscriptionService._ensure_utc_datetime(user.next_billing_date)
            
            # 如果用户有活跃订阅，从用户表读取信息
            days_remaining = None
            if expires_at:
                time_diff = expires_at - current_time
                days_remaining = max(0, time_diff.days)
            
            # 🔥 修复：确保所有字段都有值，避免null
            subscription_type = user.subscription_type or SubscriptionType.MONTHLY
            pricing_tier = user.pricing_tier or (PricingTier.EARLY_BIRD if SubscriptionService._is_early_bird_by_sequence(user) else PricingTier.STANDARD)
            
            # 如果价格层级不正确，重新计算
            if not user.pricing_tier or user.pricing_tier != pricing_tier:
                user.pricing_tier = pricing_tier
                db.commit()
            
            return SubscriptionInfo(
                is_active=True,
                subscription_type=subscription_type,
                pricing_tier=pricing_tier,
                status="active",
                monthly_price=user.monthly_price or settings.EARLY_BIRD_MONTHLY_PRICE if SubscriptionService._is_early_bird_by_sequence(user) else settings.STANDARD_MONTHLY_PRICE,
                current_price=float(user.subscription_price or user.monthly_price or settings.STANDARD_MONTHLY_PRICE),
                expires_at=expires_at,
                next_billing_date=next_billing_date,
                auto_renew=getattr(user, 'subscription_auto_renew', True),
                payment_method=getattr(user, 'payment_method', None),
                cancelled_at=SubscriptionService._ensure_utc_datetime(user.subscription_cancelled_at),
                days_remaining=days_remaining,
                started_at=SubscriptionService._ensure_utc_datetime(user.subscription_started_at),
                total_payments=float(user.total_payment_amount or 0),
                last_payment_date=SubscriptionService._ensure_utc_datetime(user.last_payment_date),
                last_payment_amount=float(user.last_payment_amount) if user.last_payment_amount else None
            )
            
        except Exception as e:
            logger.error(f"Error in get_current_subscription for user {user.id}: {str(e)}")
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
            
            # 🔥 修复：统一时区处理
            current_time = SubscriptionService._get_utc_now()
            
            if subscription_data.subscription_type == SubscriptionType.MONTHLY:
                price = pricing_info.monthly_price
                expires_at = current_time + timedelta(days=30)
            else:  # YEARLY
                price = pricing_info.yearly_price
                expires_at = current_time + timedelta(days=365)
            
            # 在 Phase 2，我们直接更新用户表
            user.tier = UserTier.PRO
            user.is_subscription_active = True
            user.subscription_type = subscription_data.subscription_type
            user.subscription_started_at = current_time
            user.subscription_expires_at = expires_at
            user.next_billing_date = expires_at
            user.subscription_price = price
            user.subscription_auto_renew = subscription_data.auto_renew
            user.payment_method = subscription_data.payment_method.value if subscription_data.payment_method else None
            user.last_payment_date = current_time
            user.last_payment_amount = price
            user.total_payment_amount = (user.total_payment_amount or 0) + price
            
            # 🔥 修复：确保早鸟状态和价格层级正确
            user.is_early_bird = SubscriptionService._is_early_bird_by_sequence(user)
            user.pricing_tier = pricing_info.pricing_tier
            user.monthly_price = pricing_info.monthly_price
            
            db.commit()
            
            logger.info(f"Subscription created for user {user.id}: type={subscription_data.subscription_type}, price=${price}, early_bird={user.is_early_bird}")
            
            return SubscriptionResponse(
                success=True,
                message="Subscription created successfully (mock)",
                subscription_info=SubscriptionService.get_current_subscription(db, user)
            )
            
        except Exception as e:
            logger.error(f"Error in create_subscription: {str(e)}")
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
            current_time = SubscriptionService._get_utc_now()
            
            if update_data.subscription_type == SubscriptionType.MONTHLY:
                new_price = pricing_info.monthly_price
                new_expires_at = current_time + timedelta(days=30)
            else:  # YEARLY
                new_price = pricing_info.yearly_price
                new_expires_at = current_time + timedelta(days=365)
            
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
            logger.error(f"Error in update_subscription: {str(e)}")
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
            
            current_time = SubscriptionService._get_utc_now()
            user.subscription_cancelled_at = current_time
            user.subscription_auto_renew = False
            
            # 🔥 修复：增强取消订阅逻辑
            if cancel_data.cancel_immediately:
                # 立即取消 - 降级为FREE用户
                user.tier = UserTier.FREE
                user.is_subscription_active = False
                user.subscription_expires_at = current_time
                message = "Subscription cancelled immediately"
                logger.info(f"User {user.id} subscription cancelled immediately")
            else:
                # 到期后取消 - 保持Pro状态直到到期
                expires_at = SubscriptionService._ensure_utc_datetime(user.subscription_expires_at)
                if expires_at:
                    expire_date = expires_at.date()
                    message = f"Subscription will be cancelled on {expire_date}"
                    logger.info(f"User {user.id} subscription scheduled for cancellation on {expire_date}")
                else:
                    # 如果没有到期时间，立即取消
                    user.tier = UserTier.FREE
                    user.is_subscription_active = False
                    user.subscription_expires_at = current_time
                    message = "Subscription cancelled immediately"
                    logger.info(f"User {user.id} subscription cancelled immediately (no expiry date)")
            
            db.commit()
            
            return SubscriptionResponse(
                success=True,
                message=message,
                subscription_info=SubscriptionService.get_current_subscription(db, user)
            )
            
        except Exception as e:
            logger.error(f"Error in cancel_subscription for user {user.id}: {str(e)}")
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to cancel subscription: {str(e)}"
            )
    
    @staticmethod
    def get_payment_history(
        db: Session,
        user: User,
        limit: int = 10
    ) -> List[PaymentHistory]:
        """获取支付历史"""
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
        """获取订阅历史"""
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
            # 🔥 修复：基于序号统计早鸟用户
            early_bird_count = db.query(func.count(User.id)).filter(
                User.user_sequence_number <= settings.EARLY_BIRD_LIMIT
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
                marketing_message = f"🦅 Early bird special: Save $10/month forever!"
            
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
            logger.error(f"Error in get_early_bird_status: {str(e)}")
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
                User.user_sequence_number <= settings.EARLY_BIRD_LIMIT
            ).scalar() or 0
            
            return {
                "total_users": total_users,
                "pro_users": pro_users,
                "free_users": total_users - pro_users,
                "early_bird_users": early_bird_users,
                "conversion_rate": (pro_users / total_users * 100) if total_users > 0 else 0
            }
        except Exception as e:
            logger.error(f"Error in get_subscription_statistics: {str(e)}")
            return {
                "total_users": 0,
                "pro_users": 0,
                "free_users": 0,
                "early_bird_users": 0,
                "conversion_rate": 0
            }

    # ==================== Apple IAP 处理方法 ====================
    
    @staticmethod
    async def process_apple_subscription(
        db: Session,
        user: User,
        receipt_info: Dict[str, Any],
        product_id: str,
        transaction_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """处理Apple订阅"""
        try:
            # 检查收据是否有效且活跃
            if not receipt_info.get("is_valid"):
                return {
                    "success": False,
                    "message": "Invalid receipt",
                    "error": receipt_info.get("error")
                }
            
            if not receipt_info.get("is_active"):
                return {
                    "success": False,
                    "message": "Subscription is not active",
                    "expires_date": receipt_info.get("expires_date")
                }
            
            # 获取订阅信息
            subscription_type = "YEARLY" if "yearly" in product_id.lower() else "MONTHLY"
            expires_date_str = receipt_info.get("expires_date")
            expires_date = None
            if expires_date_str:
                # 🔥 修复：确保时区处理正确
                try:
                    expires_date = datetime.fromisoformat(expires_date_str.replace('Z', '+00:00'))
                    if expires_date.tzinfo is None:
                        expires_date = expires_date.replace(tzinfo=timezone.utc)
                except:
                    expires_date = SubscriptionService._get_utc_now() + timedelta(days=30 if subscription_type == "MONTHLY" else 365)
            
            # 确定价格
            pricing_info = SubscriptionService.get_user_pricing(db, user)
            if subscription_type == "YEARLY":
                price = pricing_info.yearly_price
            else:
                price = pricing_info.monthly_price
            
            current_time = SubscriptionService._get_utc_now()
            
            # 更新用户订阅状态
            user.tier = UserTier.PRO
            user.is_subscription_active = True
            user.subscription_type = subscription_type
            user.subscription_started_at = user.subscription_started_at or current_time
            user.subscription_expires_at = expires_date
            user.next_billing_date = expires_date
            user.subscription_price = price
            user.subscription_auto_renew = receipt_info.get("auto_renew", True)
            user.payment_method = "apple"
            user.apple_subscription_id = receipt_info.get("original_transaction_id")
            user.last_payment_date = current_time
            user.last_payment_amount = price
            user.total_payment_amount = (user.total_payment_amount or 0) + price
            
            # 记录交易ID
            if transaction_id:
                user.last_transaction_id = transaction_id
            
            db.commit()
            
            logger.info(f"Apple subscription processed successfully for user {user.id}")
            
            return {
                "success": True,
                "message": "Subscription activated successfully",
                "subscription_info": SubscriptionService.get_current_subscription(db, user).__dict__
            }
            
        except Exception as e:
            logger.error(f"Error processing Apple subscription: {str(e)}")
            db.rollback()
            return {
                "success": False,
                "message": "Failed to process subscription",
                "error": str(e)
            }
    
    @staticmethod
    async def restore_apple_subscription(
        db: Session,
        user: User,
        receipt_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """恢复Apple订阅"""
        try:
            # 检查收据是否有效
            if not receipt_info.get("is_valid"):
                return {
                    "success": False,
                    "message": "Invalid receipt",
                    "error": receipt_info.get("error")
                }
            
            # 如果有活跃订阅，恢复它
            if receipt_info.get("is_active"):
                product_id = receipt_info.get("product_id", "")
                return await SubscriptionService.process_apple_subscription(
                    db, user, receipt_info, product_id
                )
            
            return {
                "success": False,
                "message": "No active subscription found to restore"
            }
            
        except Exception as e:
            logger.error(f"Error restoring Apple subscription: {str(e)}")
            return {
                "success": False,
                "message": "Failed to restore subscription",
                "error": str(e)
            }
    
    @staticmethod
    async def handle_apple_renewal(db: Session, notification: Dict[str, Any]):
        """处理Apple续订通知"""
        try:
            from app.services.apple_iap_service import apple_iap_service
            
            # 提取通知信息
            info = apple_iap_service.extract_notification_info(notification)
            original_transaction_id = info.get("original_transaction_id")
            
            if not original_transaction_id:
                logger.warning("No original_transaction_id in Apple renewal notification")
                return
            
            # 查找用户
            user = db.query(User).filter(
                User.apple_subscription_id == original_transaction_id
            ).first()
            
            if not user:
                logger.warning(f"User not found for Apple subscription: {original_transaction_id}")
                return
            
            # 更新订阅信息
            expires_date_str = info.get("expires_date")
            if expires_date_str:
                try:
                    expires_date = datetime.fromisoformat(expires_date_str.replace('Z', '+00:00'))
                    if expires_date.tzinfo is None:
                        expires_date = expires_date.replace(tzinfo=timezone.utc)
                    user.subscription_expires_at = expires_date
                    user.next_billing_date = expires_date
                except:
                    logger.warning(f"Failed to parse expires_date: {expires_date_str}")
            
            current_time = SubscriptionService._get_utc_now()
            user.last_payment_date = current_time
            user.last_payment_amount = user.subscription_price
            user.total_payment_amount = (user.total_payment_amount or 0) + user.subscription_price
            
            db.commit()
            logger.info(f"Apple subscription renewed for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error handling Apple renewal: {str(e)}")
            db.rollback()
    
    @staticmethod
    async def handle_apple_renewal_failure(db: Session, notification: Dict[str, Any]):
        """处理Apple续订失败通知"""
        try:
            from app.services.apple_iap_service import apple_iap_service
            
            info = apple_iap_service.extract_notification_info(notification)
            original_transaction_id = info.get("original_transaction_id")
            
            if not original_transaction_id:
                return
            
            user = db.query(User).filter(
                User.apple_subscription_id == original_transaction_id
            ).first()
            
            if not user:
                return
            
            # 标记续订失败
            user.subscription_auto_renew = False
            user.subscription_renewal_failed_at = SubscriptionService._get_utc_now()
            
            db.commit()
            logger.info(f"Apple subscription renewal failed for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error handling Apple renewal failure: {str(e)}")
            db.rollback()
    
    @staticmethod
    async def handle_apple_cancellation(db: Session, notification: Dict[str, Any]):
        """处理Apple取消通知"""
        try:
            from app.services.apple_iap_service import apple_iap_service
            
            info = apple_iap_service.extract_notification_info(notification)
            original_transaction_id = info.get("original_transaction_id")
            
            if not original_transaction_id:
                return
            
            user = db.query(User).filter(
                User.apple_subscription_id == original_transaction_id
            ).first()
            
            if not user:
                return
            
            # 标记订阅已取消
            user.subscription_cancelled_at = SubscriptionService._get_utc_now()
            user.subscription_auto_renew = False
            
            db.commit()
            logger.info(f"Apple subscription cancelled for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error handling Apple cancellation: {str(e)}")
            db.rollback()
    
    @staticmethod
    async def handle_apple_refund(db: Session, notification: Dict[str, Any]):
        """处理Apple退款通知"""
        try:
            from app.services.apple_iap_service import apple_iap_service
            
            info = apple_iap_service.extract_notification_info(notification)
            original_transaction_id = info.get("original_transaction_id")
            
            if not original_transaction_id:
                return
            
            user = db.query(User).filter(
                User.apple_subscription_id == original_transaction_id
            ).first()
            
            if not user:
                return
            
            # 处理退款：降级为免费用户
            user.tier = UserTier.FREE
            user.is_subscription_active = False
            user.subscription_refunded_at = SubscriptionService._get_utc_now()
            
            db.commit()
            logger.info(f"Apple subscription refunded for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error handling Apple refund: {str(e)}")
            db.rollback()
    
    @staticmethod
    async def handle_apple_revocation(db: Session, notification: Dict[str, Any]):
        """处理Apple撤销通知"""
        try:
            from app.services.apple_iap_service import apple_iap_service
            
            info = apple_iap_service.extract_notification_info(notification)
            original_transaction_id = info.get("original_transaction_id")
            
            if not original_transaction_id:
                return
            
            user = db.query(User).filter(
                User.apple_subscription_id == original_transaction_id
            ).first()
            
            if not user:
                return
            
            # 撤销订阅：立即失效
            current_time = SubscriptionService._get_utc_now()
            user.tier = UserTier.FREE
            user.is_subscription_active = False
            user.subscription_expires_at = current_time
            user.subscription_revoked_at = current_time
            
            db.commit()
            logger.info(f"Apple subscription revoked for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error handling Apple revocation: {str(e)}")
            db.rollback()
    
    # ==================== Google Play 处理方法 ====================
    
    @staticmethod
    async def process_google_subscription(
        db: Session,
        user: User,
        purchase_info: Dict[str, Any],
        product_id: str,
        order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """处理Google Play订阅"""
        try:
            # 检查购买是否有效且活跃
            if not purchase_info.get("is_valid"):
                return {
                    "success": False,
                    "message": "Invalid purchase",
                    "error": purchase_info.get("error")
                }
            
            if not purchase_info.get("is_active"):
                return {
                    "success": False,
                    "message": "Subscription is not active",
                    "expiry_time": purchase_info.get("expiry_time")
                }
            
            # 获取订阅信息
            subscription_type = purchase_info.get("subscription_type", "MONTHLY")
            expiry_time_str = purchase_info.get("expiry_time")
            expiry_time = None
            if expiry_time_str:
                try:
                    expiry_time = datetime.fromisoformat(expiry_time_str.replace('Z', '+00:00'))
                    if expiry_time.tzinfo is None:
                        expiry_time = expiry_time.replace(tzinfo=timezone.utc)
                except:
                    current_time = SubscriptionService._get_utc_now()
                    expiry_time = current_time + timedelta(days=30 if subscription_type == "MONTHLY" else 365)
            
            # 确定价格
            price = purchase_info.get("price")
            if not price:
                pricing_info = SubscriptionService.get_user_pricing(db, user)
                if subscription_type == "YEARLY":
                    price = pricing_info.yearly_price
                else:
                    price = pricing_info.monthly_price
            
            current_time = SubscriptionService._get_utc_now()
            
            # 更新用户订阅状态
            user.tier = UserTier.PRO
            user.is_subscription_active = True
            user.subscription_type = subscription_type
            user.subscription_started_at = user.subscription_started_at or current_time
            user.subscription_expires_at = expiry_time
            user.next_billing_date = expiry_time
            user.subscription_price = price
            user.subscription_auto_renew = purchase_info.get("auto_renewing", True)
            user.payment_method = "google"
            user.google_subscription_id = purchase_info.get("purchase_token")
            user.google_order_id = order_id or purchase_info.get("order_id")
            user.last_payment_date = current_time
            user.last_payment_amount = price
            user.total_payment_amount = (user.total_payment_amount or 0) + price
            
            db.commit()
            
            logger.info(f"Google subscription processed successfully for user {user.id}")
            
            return {
                "success": True,
                "message": "Subscription activated successfully",
                "subscription_info": SubscriptionService.get_current_subscription(db, user).__dict__
            }
            
        except Exception as e:
            logger.error(f"Error processing Google subscription: {str(e)}")
            db.rollback()
            return {
                "success": False,
                "message": "Failed to process subscription",
                "error": str(e)
            }
    
    @staticmethod
    async def handle_google_recovery(db: Session, notification_data: Dict[str, Any]):
        """处理Google订阅恢复通知"""
        try:
            from app.services.google_play_service import google_play_service
            
            info = google_play_service.process_rtdn_notification(notification_data)
            purchase_token = info.get("purchase_token")
            
            if not purchase_token:
                return
            
            user = db.query(User).filter(
                User.google_subscription_id == purchase_token
            ).first()
            
            if not user:
                logger.warning(f"User not found for Google subscription token")
                return
            
            # 恢复订阅
            user.tier = UserTier.PRO
            user.is_subscription_active = True
            user.subscription_recovered_at = SubscriptionService._get_utc_now()
            
            db.commit()
            logger.info(f"Google subscription recovered for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error handling Google recovery: {str(e)}")
            db.rollback()
    
    @staticmethod
    async def handle_google_renewal(db: Session, notification_data: Dict[str, Any]):
        """处理Google续订通知"""
        try:
            from app.services.google_play_service import google_play_service
            
            info = google_play_service.process_rtdn_notification(notification_data)
            purchase_token = info.get("purchase_token")
            product_id = info.get("product_id")
            
            if not purchase_token:
                return
            
            user = db.query(User).filter(
                User.google_subscription_id == purchase_token
            ).first()
            
            if not user:
                return
            
            # 验证最新的订阅状态
            verification = await google_play_service.verify_subscription(product_id, purchase_token)
            
            if verification.get("is_valid") and verification.get("is_active"):
                # 更新订阅信息
                expiry_time_str = verification.get("expiry_time")
                if expiry_time_str:
                    try:
                        expiry_time = datetime.fromisoformat(expiry_time_str.replace('Z', '+00:00'))
                        if expiry_time.tzinfo is None:
                            expiry_time = expiry_time.replace(tzinfo=timezone.utc)
                        user.subscription_expires_at = expiry_time
                        user.next_billing_date = expiry_time
                    except:
                        logger.warning(f"Failed to parse Google expiry_time: {expiry_time_str}")
                
                current_time = SubscriptionService._get_utc_now()
                user.last_payment_date = current_time
                user.last_payment_amount = user.subscription_price
                user.total_payment_amount = (user.total_payment_amount or 0) + user.subscription_price
                
                db.commit()
                logger.info(f"Google subscription renewed for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error handling Google renewal: {str(e)}")
            db.rollback()
    
    @staticmethod
    async def handle_google_cancellation(db: Session, notification_data: Dict[str, Any]):
        """处理Google取消通知"""
        try:
            from app.services.google_play_service import google_play_service
            
            info = google_play_service.process_rtdn_notification(notification_data)
            purchase_token = info.get("purchase_token")
            
            if not purchase_token:
                return
            
            user = db.query(User).filter(
                User.google_subscription_id == purchase_token
            ).first()
            
            if not user:
                return
            
            # 标记订阅已取消
            user.subscription_cancelled_at = SubscriptionService._get_utc_now()
            user.subscription_auto_renew = False
            
            db.commit()
            logger.info(f"Google subscription cancelled for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error handling Google cancellation: {str(e)}")
            db.rollback()
    
    @staticmethod
    async def handle_google_purchase(db: Session, notification_data: Dict[str, Any]):
        """处理Google新购买通知"""
        try:
            from app.services.google_play_service import google_play_service
            
            info = google_play_service.process_rtdn_notification(notification_data)
            purchase_token = info.get("purchase_token")
            product_id = info.get("product_id")
            
            if not purchase_token or not product_id:
                return
            
            # 验证购买
            verification = await google_play_service.verify_subscription(product_id, purchase_token)
            
            if verification.get("is_valid"):
                # 找到用户（可能需要通过其他方式关联）
                # 这里假设用户已经在应用中发起了购买请求
                logger.info(f"New Google subscription purchase: {product_id}")
            
        except Exception as e:
            logger.error(f"Error handling Google purchase: {str(e)}")
    
    @staticmethod
    async def handle_google_hold(db: Session, notification_data: Dict[str, Any]):
        """处理Google账号保留通知"""
        try:
            from app.services.google_play_service import google_play_service
            
            info = google_play_service.process_rtdn_notification(notification_data)
            purchase_token = info.get("purchase_token")
            
            if not purchase_token:
                return
            
            user = db.query(User).filter(
                User.google_subscription_id == purchase_token
            ).first()
            
            if not user:
                return
            
            # 暂停订阅（账号保留）
            user.subscription_on_hold = True
            user.subscription_hold_at = SubscriptionService._get_utc_now()
            
            db.commit()
            logger.info(f"Google subscription on hold for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error handling Google hold: {str(e)}")
            db.rollback()
    
    @staticmethod
    async def handle_google_grace_period(db: Session, notification_data: Dict[str, Any]):
        """处理Google宽限期通知"""
        try:
            from app.services.google_play_service import google_play_service
            
            info = google_play_service.process_rtdn_notification(notification_data)
            purchase_token = info.get("purchase_token")
            
            if not purchase_token:
                return
            
            user = db.query(User).filter(
                User.google_subscription_id == purchase_token
            ).first()
            
            if not user:
                return
            
            # 标记进入宽限期
            user.subscription_in_grace_period = True
            user.grace_period_started_at = SubscriptionService._get_utc_now()
            
            db.commit()
            logger.info(f"Google subscription in grace period for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error handling Google grace period: {str(e)}")
            db.rollback()
    
    @staticmethod
    async def handle_google_restart(db: Session, notification_data: Dict[str, Any]):
        """处理Google重新启动通知"""
        try:
            from app.services.google_play_service import google_play_service
            
            info = google_play_service.process_rtdn_notification(notification_data)
            purchase_token = info.get("purchase_token")
            
            if not purchase_token:
                return
            
            user = db.query(User).filter(
                User.google_subscription_id == purchase_token
            ).first()
            
            if not user:
                return
            
            # 重新激活订阅
            user.tier = UserTier.PRO
            user.is_subscription_active = True
            user.subscription_auto_renew = True
            user.subscription_restarted_at = SubscriptionService._get_utc_now()
            
            # 清除保留和宽限期标记
            user.subscription_on_hold = False
            user.subscription_in_grace_period = False
            
            db.commit()
            logger.info(f"Google subscription restarted for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error handling Google restart: {str(e)}")
            db.rollback()
    
    @staticmethod
    async def handle_google_revocation(db: Session, notification_data: Dict[str, Any]):
        """处理Google撤销通知"""
        try:
            from app.services.google_play_service import google_play_service
            
            info = google_play_service.process_rtdn_notification(notification_data)
            purchase_token = info.get("purchase_token")
            
            if not purchase_token:
                return
            
            user = db.query(User).filter(
                User.google_subscription_id == purchase_token
            ).first()
            
            if not user:
                return
            
            # 撤销订阅：立即失效
            current_time = SubscriptionService._get_utc_now()
            user.tier = UserTier.FREE
            user.is_subscription_active = False
            user.subscription_expires_at = current_time
            user.subscription_revoked_at = current_time
            
            db.commit()
            logger.info(f"Google subscription revoked for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error handling Google revocation: {str(e)}")
            db.rollback()
    
    @staticmethod
    async def handle_google_expiration(db: Session, notification_data: Dict[str, Any]):
        """处理Google过期通知"""
        try:
            from app.services.google_play_service import google_play_service
            
            info = google_play_service.process_rtdn_notification(notification_data)
            purchase_token = info.get("purchase_token")
            
            if not purchase_token:
                return
            
            user = db.query(User).filter(
                User.google_subscription_id == purchase_token
            ).first()
            
            if not user:
                return
            
            # 订阅过期
            user.tier = UserTier.FREE
            user.is_subscription_active = False
            user.subscription_expired_at = SubscriptionService._get_utc_now()
            
            db.commit()
            logger.info(f"Google subscription expired for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error handling Google expiration: {str(e)}")
            db.rollback()


# 创建服务实例
subscription_service = SubscriptionService()
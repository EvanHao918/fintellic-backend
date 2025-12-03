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
    PaymentHistory,
    SubscriptionHistory
)

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Production-ready subscription service - Phase 2"""
    
    @staticmethod
    def _get_utc_now() -> datetime:
        """Get UTC time ensuring timezone consistency"""
        return datetime.now(timezone.utc)
    
    @staticmethod
    def _ensure_utc_datetime(dt: Optional[datetime]) -> Optional[datetime]:
        """Ensure datetime is UTC timezone aware"""
        if dt is None:
            return None
        if dt.tzinfo is None:
            # If naive datetime, assume UTC
            return dt.replace(tzinfo=timezone.utc)
        return dt
    
    @staticmethod
    def get_user_pricing(db: Session, user: User) -> PricingInfo:
        """
        Get user pricing information - Monthly only
        Based on system configuration (USE_DISCOUNTED_PRICING flag)
        """
        try:
            # Get current system pricing configuration
            pricing_config = settings.get_pricing_info()
            
            monthly_price = pricing_config["monthly_price"]
            is_discounted = pricing_config["is_discounted"]
            
            # Determine pricing tier (maintain backward compatibility)
            pricing_tier = PricingTier.EARLY_BIRD if is_discounted else PricingTier.STANDARD
            
            return PricingInfo(
                is_early_bird=is_discounted,  # Backward compatibility
                is_discounted=is_discounted,
                user_sequence_number=user.user_sequence_number,
                pricing_tier=pricing_tier,
                monthly_price=monthly_price,
                currency="USD",
                features={
                    "unlimited_reports": True,
                    "ai_analysis": True,
                    "push_notifications": True,
                    "priority_support": True,
                    "early_access": True
                }
            )
        except Exception as e:
            logger.error(f"Error in get_user_pricing: {str(e)}")
            raise
    
    @staticmethod
    def get_current_subscription(db: Session, user: User) -> SubscriptionInfo:
        """Get user's current subscription information"""
        try:
            # Check if user has active subscription
            if not user.is_subscription_active:
                return SubscriptionInfo(
                    is_active=False,
                    status="pending",
                    monthly_price=settings.current_monthly_price,
                    auto_renew=False,
                    total_payments=float(user.total_payment_amount or 0)
                )
            
            # Unified timezone handling
            current_time = SubscriptionService._get_utc_now()
            expires_at = SubscriptionService._ensure_utc_datetime(user.subscription_expires_at)
            next_billing_date = SubscriptionService._ensure_utc_datetime(user.next_billing_date)
            
            # Calculate days remaining
            days_remaining = None
            if expires_at:
                time_diff = expires_at - current_time
                days_remaining = max(0, time_diff.days)
            
            # Ensure all fields have values
            subscription_type = user.subscription_type or SubscriptionType.MONTHLY
            pricing_tier = user.pricing_tier or (PricingTier.EARLY_BIRD if settings.is_discounted_pricing else PricingTier.STANDARD)
            
            # Update pricing tier if incorrect
            if not user.pricing_tier or user.pricing_tier != pricing_tier:
                user.pricing_tier = pricing_tier
                db.commit()
            
            return SubscriptionInfo(
                is_active=True,
                subscription_type=subscription_type,
                pricing_tier=pricing_tier,
                status="active",
                monthly_price=user.monthly_price or settings.current_monthly_price,
                current_price=float(user.subscription_price or user.monthly_price or settings.current_monthly_price),
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
            # Return basic info if query fails
            return SubscriptionInfo(
                is_active=user.tier == UserTier.PRO,
                status="active" if user.tier == UserTier.PRO else "pending",
                monthly_price=user.monthly_price or settings.current_monthly_price,
                auto_renew=False,
                total_payments=0
            )
    
    @staticmethod
    def create_subscription(
        db: Session, 
        user: User, 
        subscription_data: SubscriptionCreate
    ) -> SubscriptionResponse:
        """Create new subscription - REMOVED MOCK LOGIC"""
        try:
            # Phase 2: Real payment creation should be handled by payment verification endpoints
            # This method now only validates and returns payment required
            
            if user.is_subscription_active:
                return SubscriptionResponse(
                    success=False,
                    message="You already have an active subscription",
                    subscription_info=SubscriptionService.get_current_subscription(db, user),
                    payment_required=False
                )
            
            # Get pricing information (monthly only)
            pricing_info = SubscriptionService.get_user_pricing(db, user)
            price = pricing_info.monthly_price
            
            logger.info(f"Subscription creation requested for user {user.id}: type=MONTHLY, price=${price}")
            
            return SubscriptionResponse(
                success=False,
                message="Payment required - Please complete purchase through Apple App Store",
                subscription_info=None,
                payment_required=True
            )
            
        except Exception as e:
            logger.error(f"Error in create_subscription for user {user.id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initiate subscription"
            )
            
            # Phase 2: Direct subscription creation only for development
            if settings.ENABLE_MOCK_PAYMENTS and settings.is_development:
                return SubscriptionService._create_mock_subscription(db, user, subscription_data, pricing_info)
            
            # Production: Require real payment verification
            return SubscriptionResponse(
                success=False,
                message="Please complete payment through the mobile app",
                subscription_info=None,
                payment_required=True
            )
            
        except Exception as e:
            logger.error(f"Error in create_subscription: {str(e)}")
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create subscription: {str(e)}"
            )
    
    @staticmethod
    def _create_mock_subscription(
        db: Session,
        user: User,
        subscription_data: SubscriptionCreate,
        pricing_info: PricingInfo
    ) -> SubscriptionResponse:
        """Create mock subscription for development only"""
        try:
            current_time = SubscriptionService._get_utc_now()
            
            if subscription_data.subscription_type == SubscriptionType.MONTHLY:
                price = pricing_info.monthly_price
                expires_at = current_time + timedelta(days=30)
            else:  # YEARLY
                price = pricing_info.yearly_price
                expires_at = current_time + timedelta(days=365)
            
            # Update user subscription status
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
            
            # Set pricing tier
            user.pricing_tier = pricing_info.pricing_tier
            user.subscription_price = pricing_info.monthly_price  # Use subscription_price instead of monthly_price
            user.is_early_bird = pricing_info.is_early_bird
            
            db.commit()
            
            logger.info(f"Mock subscription created for user {user.id}: type={subscription_data.subscription_type}, price=${price}")
            
            return SubscriptionResponse(
                success=True,
                message="Subscription created successfully (development mode)",
                subscription_info=SubscriptionService.get_current_subscription(db, user),
                payment_required=False
            )
            
        except Exception as e:
            logger.error(f"Error creating mock subscription: {str(e)}")
            db.rollback()
            raise
    
    @staticmethod
    def update_subscription(
        db: Session,
        user: User,
        update_data: SubscriptionUpdate
    ) -> SubscriptionResponse:
        """Update subscription (switch monthly/yearly)"""
        try:
            if not user.is_subscription_active:
                return SubscriptionResponse(
                    success=False,
                    message="No active subscription found",
                    subscription_info=None,
                    payment_required=False
                )
            
            # If same type, no need to update
            if user.subscription_type == update_data.subscription_type:
                return SubscriptionResponse(
                    success=False,
                    message="You are already on this plan",
                    subscription_info=SubscriptionService.get_current_subscription(db, user),
                    payment_required=False
                )
            
            # Calculate new price and expiry time
            pricing_info = SubscriptionService.get_user_pricing(db, user)
            current_time = SubscriptionService._get_utc_now()
            
            if update_data.subscription_type == SubscriptionType.MONTHLY:
                new_price = pricing_info.monthly_price
                new_expires_at = current_time + timedelta(days=30)
            else:  # YEARLY
                new_price = pricing_info.yearly_price
                new_expires_at = current_time + timedelta(days=365)
            
            # Update user
            user.subscription_type = update_data.subscription_type
            user.subscription_price = new_price
            if update_data.immediate:
                user.subscription_expires_at = new_expires_at
                user.next_billing_date = new_expires_at
            
            db.commit()
            
            return SubscriptionResponse(
                success=True,
                message=f"Subscription updated to {update_data.subscription_type.value}",
                subscription_info=SubscriptionService.get_current_subscription(db, user),
                payment_required=False
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
        """Cancel subscription"""
        try:
            if not user.is_subscription_active:
                return SubscriptionResponse(
                    success=False,
                    message="No active subscription found",
                    subscription_info=None,
                    payment_required=False
                )
            
            current_time = SubscriptionService._get_utc_now()
            user.subscription_cancelled_at = current_time
            user.subscription_auto_renew = False
            
            if cancel_data.cancel_immediately:
                # Immediate cancellation
                user.tier = UserTier.FREE
                user.is_subscription_active = False
                user.subscription_expires_at = current_time
                message = "Subscription cancelled immediately"
                logger.info(f"User {user.id} subscription cancelled immediately")
            else:
                # Cancel at expiry
                expires_at = SubscriptionService._ensure_utc_datetime(user.subscription_expires_at)
                if expires_at:
                    expire_date = expires_at.date()
                    message = f"Subscription will be cancelled on {expire_date}"
                    logger.info(f"User {user.id} subscription scheduled for cancellation on {expire_date}")
                else:
                    # No expiry date, cancel immediately
                    user.tier = UserTier.FREE
                    user.is_subscription_active = False
                    user.subscription_expires_at = current_time
                    message = "Subscription cancelled immediately"
                    logger.info(f"User {user.id} subscription cancelled immediately (no expiry date)")
            
            db.commit()
            
            return SubscriptionResponse(
                success=True,
                message=message,
                subscription_info=SubscriptionService.get_current_subscription(db, user),
                payment_required=False
            )
            
        except Exception as e:
            logger.error(f"Error in cancel_subscription for user {user.id}: {str(e)}")
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to cancel subscription: {str(e)}"
            )
    
    # ==================== REAL PAYMENT PROCESSING METHODS ====================
    
    @staticmethod
    async def process_apple_subscription(
        db: Session,
        user: User,
        receipt_info: Dict[str, Any],
        product_id: str,
        transaction_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process Apple subscription with real payment verification"""
        try:
            # Validate receipt
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
            
            # Validate product ID
            from app.services.apple_iap_service import apple_iap_service
            if not apple_iap_service.validate_product_id(product_id):
                return {
                    "success": False,
                    "message": "Invalid product ID"
                }
            
            # Get subscription info
            subscription_type = "YEARLY" if "yearly" in product_id.lower() else "MONTHLY"
            expires_date_str = receipt_info.get("expires_date")
            expires_date = None
            
            if expires_date_str:
                try:
                    expires_date = datetime.fromisoformat(expires_date_str.replace('Z', '+00:00'))
                    if expires_date.tzinfo is None:
                        expires_date = expires_date.replace(tzinfo=timezone.utc)
                except Exception as e:
                    logger.warning(f"Failed to parse expires_date: {expires_date_str}, error: {e}")
                    expires_date = SubscriptionService._get_utc_now() + timedelta(days=30 if subscription_type == "MONTHLY" else 365)
            
            # Determine price
            if subscription_type == "YEARLY":
                price = settings.current_yearly_price
            else:
                price = settings.current_monthly_price
            
            current_time = SubscriptionService._get_utc_now()
            
            # Update user subscription status
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
            
            # Set pricing tier
            user.pricing_tier = PricingTier.EARLY_BIRD if settings.is_discounted_pricing else PricingTier.STANDARD
            user.subscription_price = settings.current_monthly_price  # Use subscription_price instead of monthly_price
            user.is_early_bird = settings.is_discounted_pricing
            
            # Record transaction ID
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
        """Restore Apple subscription"""
        try:
            if not receipt_info.get("is_valid"):
                return {
                    "success": False,
                    "message": "Invalid receipt",
                    "error": receipt_info.get("error")
                }
            
            # If has active subscription, restore it
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
    
    # ==================== GOOGLE PLAY (DISABLED - iOS ONLY) ====================
    
    @staticmethod
    async def process_google_subscription(
        db: Session,
        user: User,
        purchase_info: Dict[str, Any],
        product_id: str,
        order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process Google Play subscription - DISABLED
        iOS-only mode: Google Play subscriptions not supported
        Kept for potential future Android expansion
        """
        logger.warning(f"Google Play subscription attempted by user {user.id} but iOS-only mode enabled")
        return {
            "success": False,
            "message": "Google Play subscriptions not supported - iOS only",
            "error": "PLATFORM_NOT_SUPPORTED"
        }
    
    # ==================== WEBHOOK HANDLERS ====================
    
    @staticmethod
    async def handle_apple_renewal(db: Session, notification: Dict[str, Any]):
        """Handle Apple renewal notification"""
        try:
            from app.services.apple_iap_service import apple_iap_service
            
            # Extract notification info
            info = apple_iap_service.extract_notification_info(notification)
            original_transaction_id = info.get("original_transaction_id")
            
            if not original_transaction_id:
                logger.warning("No original_transaction_id in Apple renewal notification")
                return
            
            # Find user
            user = db.query(User).filter(
                User.apple_subscription_id == original_transaction_id
            ).first()
            
            if not user:
                logger.warning(f"User not found for Apple subscription: {original_transaction_id}")
                return
            
            # Update subscription info
            expires_date_str = info.get("expires_date")
            if expires_date_str:
                try:
                    expires_date = datetime.fromisoformat(expires_date_str.replace('Z', '+00:00'))
                    if expires_date.tzinfo is None:
                        expires_date = expires_date.replace(tzinfo=timezone.utc)
                    user.subscription_expires_at = expires_date
                    user.next_billing_date = expires_date
                except Exception as e:
                    logger.warning(f"Failed to parse expires_date: {expires_date_str}, error: {e}")
            
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
    def get_payment_history(
        db: Session,
        user: User,
        limit: int = 10
    ) -> List[PaymentHistory]:
        """Get payment history"""
        history = []
        if user.last_payment_date and user.last_payment_amount:
            history.append(
                PaymentHistory(
                    id=1,
                    amount=float(user.last_payment_amount),
                    currency="USD",
                    payment_method=user.payment_method or "card",
                    payment_status="success",
                    transaction_id=f"txn_{user.id}_{int(user.last_payment_date.timestamp())}",
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
        """Get subscription history"""
        history = []
        if user.subscription_started_at:
            history.append(
                SubscriptionHistory(
                    id=1,
                    subscription_type=user.subscription_type.value if user.subscription_type else "MONTHLY",
                    pricing_tier=user.pricing_tier.value if user.pricing_tier else "STANDARD",
                    price=float(user.subscription_price or user.monthly_price or settings.current_monthly_price),
                    started_at=user.subscription_started_at,
                    expires_at=user.subscription_expires_at,
                    status="active" if user.is_subscription_active else "expired",
                    cancelled_at=user.subscription_cancelled_at
                )
            )
        return history
    
    @staticmethod
    def get_subscription_statistics(db: Session) -> Dict[str, Any]:
        """Get subscription statistics (admin)"""
        try:
            total_users = db.query(func.count(User.id)).scalar() or 0
            pro_users = db.query(func.count(User.id)).filter(
                User.tier == UserTier.PRO
            ).scalar() or 0
            
            # Count users with discounted pricing
            discounted_users = db.query(func.count(User.id)).filter(
                and_(
                    User.tier == UserTier.PRO,
                    User.pricing_tier == PricingTier.EARLY_BIRD
                )
            ).scalar() or 0
            
            return {
                "total_users": total_users,
                "pro_users": pro_users,
                "free_users": total_users - pro_users,
                "discounted_users": discounted_users,
                "standard_users": pro_users - discounted_users,
                "conversion_rate": (pro_users / total_users * 100) if total_users > 0 else 0,
                "current_pricing": {
                    "monthly_price": settings.current_monthly_price,
                    "is_discounted": settings.is_discounted_pricing
                }
            }
        except Exception as e:
            logger.error(f"Error in get_subscription_statistics: {str(e)}")
            return {
                "total_users": 0,
                "pro_users": 0,
                "free_users": 0,
                "discounted_users": 0,
                "standard_users": 0,
                "conversion_rate": 0,
                "current_pricing": {
                    "monthly_price": settings.current_monthly_price,
                    "is_discounted": settings.is_discounted_pricing
                }
            }


# Create service instance
subscription_service = SubscriptionService()
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from sqlalchemy.orm import Session
import json
import logging

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.services.subscription_service import subscription_service
from app.core.config import settings
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionUpdate,
    SubscriptionCancel,
    SubscriptionResponse,
    SubscriptionInfo,
    PricingInfo,
    EarlyBirdStatus,
    PaymentHistory,
    SubscriptionHistory,
    CreateCheckoutSession,
    CheckoutSessionResponse
)

# 导入支付验证服务
from app.services.apple_iap_service import apple_iap_service
from app.services.google_play_service import google_play_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/pricing", response_model=PricingInfo)
def get_pricing(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get personalized pricing for the current user
    """
    return subscription_service.get_user_pricing(db, current_user)


@router.get("/current", response_model=SubscriptionInfo)
def get_current_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get current subscription status
    """
    return subscription_service.get_current_subscription(db, current_user)


@router.post("/create", response_model=SubscriptionResponse)
def create_subscription(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    subscription_data: SubscriptionCreate
) -> Any:
    """
    Create a new subscription (Mock in development, real in production)
    """
    if current_user.is_subscription_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an active subscription"
        )
    
    # 在开发环境使用Mock
    if settings.ENABLE_MOCK_PAYMENTS and settings.ENVIRONMENT == "development":
        return subscription_service.create_subscription(db, current_user, subscription_data)
    else:
        # 生产环境需要真实支付验证
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Please complete payment through the mobile app"
        )


@router.put("/update", response_model=SubscriptionResponse)
def update_subscription(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    update_data: SubscriptionUpdate
) -> Any:
    """
    Update subscription (switch between monthly/yearly)
    """
    if not current_user.is_subscription_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription found"
        )
    
    return subscription_service.update_subscription(db, current_user, update_data)


@router.post("/cancel", response_model=SubscriptionResponse)
def cancel_subscription(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    cancel_data: SubscriptionCancel
) -> Any:
    """
    Cancel subscription
    """
    if not current_user.is_subscription_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription found"
        )
    
    return subscription_service.cancel_subscription(db, current_user, cancel_data)


@router.get("/history", response_model=List[SubscriptionHistory])
def get_subscription_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get subscription history
    """
    return subscription_service.get_subscription_history(db, current_user)


@router.get("/payments", response_model=List[PaymentHistory])
def get_payment_history(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=100)
) -> Any:
    """
    Get payment history
    """
    return subscription_service.get_payment_history(db, current_user, limit)


@router.get("/early-bird-status", response_model=EarlyBirdStatus)
def get_early_bird_status(db: Session = Depends(get_db)) -> Any:
    """
    Get early bird availability status
    """
    return subscription_service.get_early_bird_status(db)


# ==================== Apple IAP 验证端点 ====================

@router.post("/verify/apple")
async def verify_apple_purchase(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    receipt_data: str = Body(..., description="Base64 encoded receipt"),
    product_id: str = Body(..., description="Product ID from the purchase"),
    transaction_id: Optional[str] = Body(None, description="Transaction ID")
) -> Any:
    """
    Verify Apple In-App Purchase receipt
    """
    try:
        # 验证收据
        verification_result = await apple_iap_service.verify_receipt(
            receipt_data=receipt_data,
            exclude_old_transactions=True
        )
        
        if not verification_result.get("is_valid"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid receipt: {verification_result.get('error', 'Unknown error')}"
            )
        
        # 处理订阅
        result = await subscription_service.process_apple_subscription(
            db=db,
            user=current_user,
            receipt_info=verification_result,
            product_id=product_id,
            transaction_id=transaction_id
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Apple IAP verification error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {str(e)}"
        )


@router.post("/restore/apple")
async def restore_apple_purchases(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    receipt_data: str = Body(..., description="Base64 encoded receipt")
) -> Any:
    """
    Restore Apple purchases
    """
    try:
        # 验证收据并恢复所有购买
        verification_result = await apple_iap_service.verify_receipt(
            receipt_data=receipt_data,
            exclude_old_transactions=False
        )
        
        if not verification_result.get("is_valid"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid receipt"
            )
        
        # 恢复订阅
        result = await subscription_service.restore_apple_subscription(
            db=db,
            user=current_user,
            receipt_info=verification_result
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Apple restore error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restore failed: {str(e)}"
        )


# ==================== Google Play 验证端点 ====================

@router.post("/verify/google")
async def verify_google_purchase(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    purchase_token: str = Body(..., description="Purchase token from Google"),
    product_id: str = Body(..., description="Product ID"),
    order_id: Optional[str] = Body(None, description="Order ID")
) -> Any:
    """
    Verify Google Play purchase
    """
    try:
        # 验证购买
        verification_result = await google_play_service.verify_subscription(
            product_id=product_id,
            purchase_token=purchase_token
        )
        
        if not verification_result.get("is_valid"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid purchase: {verification_result.get('error', 'Unknown error')}"
            )
        
        # 处理订阅
        result = await subscription_service.process_google_subscription(
            db=db,
            user=current_user,
            purchase_info=verification_result,
            product_id=product_id,
            order_id=order_id
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google Play verification error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {str(e)}"
        )


# ==================== Webhook 端点 ====================

@router.post("/webhook/apple")
async def apple_webhook(
    request: Request,
    db: Session = Depends(get_db)
) -> Any:
    """
    Handle Apple Server-to-Server notifications
    """
    try:
        # 获取请求体
        body = await request.body()
        
        # 解析通知
        try:
            notification = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in Apple webhook")
            return {"status": "error", "message": "Invalid JSON"}
        
        # 验证通知签名
        if not apple_iap_service.verify_notification(notification):
            logger.warning("Invalid Apple notification signature")
            # 不返回错误状态码，避免重试
            return {"status": "error", "message": "Invalid signature"}
        
        # 处理不同类型的通知
        notification_type = notification.get("notification_type") or notification.get("notificationType")
        
        logger.info(f"Processing Apple webhook: {notification_type}")
        
        if notification_type in ["DID_RENEW", "INTERACTIVE_RENEWAL"]:
            await subscription_service.handle_apple_renewal(db, notification)
        elif notification_type in ["DID_FAIL_TO_RENEW", "GRACE_PERIOD_EXPIRED"]:
            await subscription_service.handle_apple_renewal_failure(db, notification)
        elif notification_type in ["CANCEL", "DID_CHANGE_RENEWAL_STATUS"]:
            await subscription_service.handle_apple_cancellation(db, notification)
        elif notification_type == "REFUND":
            await subscription_service.handle_apple_refund(db, notification)
        elif notification_type == "REVOKE":
            await subscription_service.handle_apple_revocation(db, notification)
        else:
            logger.info(f"Unhandled Apple notification type: {notification_type}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Apple webhook error: {str(e)}", exc_info=True)
        # Webhook应该总是返回200，避免重试
        return {"status": "error", "message": str(e)}


@router.post("/webhook/google")
async def google_webhook(
    request: Request,
    db: Session = Depends(get_db)
) -> Any:
    """
    Handle Google Play Real-time Developer Notifications
    """
    try:
        # 获取请求体
        body = await request.body()
        
        # 解析通知
        try:
            notification = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in Google webhook")
            return {"status": "error", "message": "Invalid JSON"}
        
        # Google使用Cloud Pub/Sub，消息在message.data中
        message = notification.get("message", {})
        data = message.get("data", "")
        
        if not data:
            logger.warning("No data in Google notification")
            return {"status": "error", "message": "No data"}
        
        # 解码base64数据
        import base64
        try:
            decoded_data = json.loads(base64.b64decode(data))
        except Exception as e:
            logger.error(f"Failed to decode Google notification data: {e}")
            return {"status": "error", "message": "Invalid data encoding"}
        
        # 获取通知类型
        subscription_notification = decoded_data.get("subscriptionNotification", {})
        notification_type = subscription_notification.get("notificationType")
        
        logger.info(f"Processing Google webhook: {notification_type}")
        
        # 处理不同类型的通知
        if notification_type == 1:  # SUBSCRIPTION_RECOVERED
            await subscription_service.handle_google_recovery(db, decoded_data)
        elif notification_type == 2:  # SUBSCRIPTION_RENEWED
            await subscription_service.handle_google_renewal(db, decoded_data)
        elif notification_type == 3:  # SUBSCRIPTION_CANCELED
            await subscription_service.handle_google_cancellation(db, decoded_data)
        elif notification_type == 4:  # SUBSCRIPTION_PURCHASED
            await subscription_service.handle_google_purchase(db, decoded_data)
        elif notification_type == 5:  # SUBSCRIPTION_ON_HOLD
            await subscription_service.handle_google_hold(db, decoded_data)
        elif notification_type == 6:  # SUBSCRIPTION_IN_GRACE_PERIOD
            await subscription_service.handle_google_grace_period(db, decoded_data)
        elif notification_type == 7:  # SUBSCRIPTION_RESTARTED
            await subscription_service.handle_google_restart(db, decoded_data)
        elif notification_type == 12:  # SUBSCRIPTION_REVOKED
            await subscription_service.handle_google_revocation(db, decoded_data)
        elif notification_type == 13:  # SUBSCRIPTION_EXPIRED
            await subscription_service.handle_google_expiration(db, decoded_data)
        else:
            logger.info(f"Unhandled Google notification type: {notification_type}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Google webhook error: {str(e)}", exc_info=True)
        # Webhook应该总是返回200，避免重试
        return {"status": "error", "message": str(e)}


# ==================== 开发测试端点 ====================

@router.post("/mock/upgrade")
async def mock_upgrade_to_pro(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    subscription_type: str = Body("MONTHLY", description="MONTHLY or YEARLY")
) -> Any:
    """
    Mock upgrade to Pro (development only)
    """
    if not settings.ENABLE_MOCK_PAYMENTS or settings.ENVIRONMENT != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mock payments are disabled in production"
        )
    
    # 创建Mock订阅
    subscription_data = SubscriptionCreate(
        subscription_type=subscription_type,
        payment_method="mock",
        auto_renew=True
    )
    
    return subscription_service.create_subscription(db, current_user, subscription_data)


# Admin endpoints (if needed)
@router.get("/admin/statistics")
def get_subscription_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get subscription statistics (admin only)
    """
    # Check if user is admin
    if not getattr(current_user, 'is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access admin statistics"
        )
    
    return subscription_service.get_subscription_statistics(db)
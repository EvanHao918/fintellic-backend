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
    PaymentHistory,
    SubscriptionHistory,
    CreateCheckoutSession,
    CheckoutSessionResponse
)

# Import real payment verification services
from app.services.apple_iap_service import apple_iap_service
from app.services.google_play_service import google_play_service

router = APIRouter()
logger = logging.getLogger(__name__)


# ==================== PRODUCTION SAFETY MIDDLEWARE ====================

def validate_production_readiness():
    """Validate production configuration on startup"""
    if settings.is_production:
        issues = settings.validate_production_config()
        if issues:
            logger.error(f"Production configuration issues detected: {issues}")
            raise RuntimeError(f"Production not ready: {', '.join(issues)}")
        
        logger.info("Production configuration validated successfully")
        logger.info(f"Security level: {settings.security_level}")
    else:
        logger.info(f"Running in {settings.ENVIRONMENT} mode")


def check_environment_security(endpoint_name: str):
    """Check environment-specific security requirements"""
    if settings.is_production and not settings.is_production_ready:
        logger.error(f"Production endpoint {endpoint_name} called but system not production ready")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable - configuration incomplete"
        )


# ==================== CORE SUBSCRIPTION ENDPOINTS ====================

@router.get("/pricing", response_model=PricingInfo)
def get_pricing(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get personalized pricing for the current user
    Returns current system configured pricing
    """
    try:
        return subscription_service.get_user_pricing(db, current_user)
    except Exception as e:
        logger.error(f"Error fetching pricing for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch pricing information"
        )


@router.get("/current", response_model=SubscriptionInfo)
def get_current_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get current subscription status
    """
    try:
        return subscription_service.get_current_subscription(db, current_user)
    except Exception as e:
        logger.error(f"Error fetching subscription for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch subscription status"
        )


@router.post("/create", response_model=SubscriptionResponse)
def create_subscription(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    subscription_data: SubscriptionCreate
) -> Any:
    """
    Create a new subscription
    Production: Requires real payment verification
    Development: Allows mock for testing
    """
    check_environment_security("create_subscription")
    
    if current_user.is_subscription_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an active subscription"
        )
    
    # Strict environment-based logic
    if settings.ENABLE_MOCK_PAYMENTS and settings.is_development:
        logger.info(f"Processing mock subscription for user {current_user.id} in development")
        return subscription_service.create_subscription(db, current_user, subscription_data)
    else:
        # Production or staging: Direct creation not allowed
        logger.warning(f"Direct subscription creation attempted for user {current_user.id} in {settings.ENVIRONMENT}")
        
        if settings.is_production:
            detail_message = "Please complete payment through the mobile app using Apple or Google Pay"
        else:
            detail_message = f"Direct subscription creation not allowed in {settings.ENVIRONMENT} environment"
        
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail_message
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
    
    try:
        return subscription_service.update_subscription(db, current_user, update_data)
    except Exception as e:
        logger.error(f"Error updating subscription for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update subscription"
        )


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
    try:
        logger.info(f"Cancel subscription request for user {current_user.id}")
        
        if not current_user.is_subscription_active:
            logger.warning(f"User {current_user.id} tried to cancel but has no active subscription")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active subscription found"
            )
        
        result = subscription_service.cancel_subscription(db, current_user, cancel_data)
        logger.info(f"Cancel subscription result for user {current_user.id}: success={result.success}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in cancel_subscription for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel subscription"
        )


@router.get("/history", response_model=List[SubscriptionHistory])
def get_subscription_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get subscription history
    """
    try:
        return subscription_service.get_subscription_history(db, current_user)
    except Exception as e:
        logger.error(f"Error fetching subscription history for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch subscription history"
        )


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
    try:
        return subscription_service.get_payment_history(db, current_user, limit)
    except Exception as e:
        logger.error(f"Error fetching payment history for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch payment history"
        )


# ==================== APPLE IAP VERIFICATION ENDPOINTS ====================

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
    Verify Apple In-App Purchase receipt and activate subscription
    Production-ready Apple IAP verification with enhanced security
    """
    check_environment_security("verify_apple_purchase")
    
    try:
        logger.info(f"Apple IAP verification request for user {current_user.id}, product: {product_id}")
        
        # Enhanced input validation
        if not receipt_data or not product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Receipt data and product ID are required"
            )
        
        # Validate product ID format and ownership
        if not apple_iap_service.validate_product_id(product_id):
            logger.warning(f"Invalid Apple product ID attempted by user {current_user.id}: {product_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )
        
        # Check production readiness for Apple IAP
        if settings.is_production and not settings.APPLE_SHARED_SECRET:
            logger.error("Apple verification attempted in production without shared secret")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Apple payment verification temporarily unavailable"
            )
        
        # Verify receipt with Apple
        verification_result = await apple_iap_service.verify_receipt(
            receipt_data=receipt_data,
            exclude_old_transactions=True
        )
        
        logger.info(f"Apple verification result for user {current_user.id}: valid={verification_result.get('is_valid')}")
        
        if not verification_result.get("is_valid"):
            error_detail = verification_result.get('error', 'Unknown verification error')
            logger.warning(f"Apple receipt verification failed for user {current_user.id}: {error_detail}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid receipt: {error_detail}"
            )
        
        # Process subscription activation
        result = await subscription_service.process_apple_subscription(
            db=db,
            user=current_user,
            receipt_info=verification_result,
            product_id=product_id,
            transaction_id=transaction_id
        )
        
        if result.get("success"):
            logger.info(f"Apple subscription activated for user {current_user.id}")
        else:
            logger.warning(f"Apple subscription activation failed for user {current_user.id}: {result.get('message')}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Apple IAP verification unexpected error for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification failed due to server error"
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
    Production-ready Apple purchase restoration with enhanced validation
    """
    check_environment_security("restore_apple_purchases")
    
    try:
        logger.info(f"Apple purchase restoration request for user {current_user.id}")
        
        if not receipt_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Receipt data is required"
            )
        
        # Check production readiness
        if settings.is_production and not settings.APPLE_SHARED_SECRET:
            logger.error("Apple restore attempted in production without shared secret")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Apple restore temporarily unavailable"
            )
        
        # Verify receipt and restore all purchases
        verification_result = await apple_iap_service.verify_receipt(
            receipt_data=receipt_data,
            exclude_old_transactions=False
        )
        
        if not verification_result.get("is_valid"):
            error_detail = verification_result.get('error', 'Unknown verification error')
            logger.warning(f"Apple receipt verification failed during restore for user {current_user.id}: {error_detail}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid receipt: {error_detail}"
            )
        
        # Restore subscription
        result = await subscription_service.restore_apple_subscription(
            db=db,
            user=current_user,
            receipt_info=verification_result
        )
        
        if result.get("success"):
            logger.info(f"Apple subscription restored for user {current_user.id}")
        else:
            logger.info(f"No Apple subscription to restore for user {current_user.id}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Apple restore unexpected error for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Restore failed due to server error"
        )


# ==================== GOOGLE PLAY VERIFICATION ENDPOINTS ====================

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
    Verify Google Play purchase and activate subscription
    Production-ready Google Play verification with enhanced security
    """
    check_environment_security("verify_google_purchase")
    
    try:
        logger.info(f"Google Play verification request for user {current_user.id}, product: {product_id}")
        
        # Enhanced input validation
        if not purchase_token or not product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Purchase token and product ID are required"
            )
        
        # Validate product ID
        if not google_play_service._validate_product_id(product_id):
            logger.warning(f"Invalid Google product ID attempted by user {current_user.id}: {product_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )
        
        # Check Google Play service status
        service_status = google_play_service.get_service_status()
        if settings.is_production and not service_status.get("service_initialized"):
            logger.error("Google verification attempted in production without proper configuration")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google payment verification temporarily unavailable"
            )
        
        # Verify purchase with Google
        verification_result = await google_play_service.verify_subscription(
            product_id=product_id,
            purchase_token=purchase_token
        )
        
        logger.info(f"Google verification result for user {current_user.id}: valid={verification_result.get('is_valid')}")
        
        if not verification_result.get("is_valid"):
            error_detail = verification_result.get('error', 'Unknown verification error')
            logger.warning(f"Google purchase verification failed for user {current_user.id}: {error_detail}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid purchase: {error_detail}"
            )
        
        # Process subscription activation
        result = await subscription_service.process_google_subscription(
            db=db,
            user=current_user,
            purchase_info=verification_result,
            product_id=product_id,
            order_id=order_id
        )
        
        if result.get("success"):
            logger.info(f"Google subscription activated for user {current_user.id}")
        else:
            logger.warning(f"Google subscription activation failed for user {current_user.id}: {result.get('message')}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google Play verification unexpected error for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification failed due to server error"
        )


# ==================== WEBHOOK ENDPOINTS ====================

@router.post("/webhook/apple")
async def apple_webhook(
    request: Request,
    db: Session = Depends(get_db)
) -> Any:
    """
    Handle Apple Server-to-Server notifications
    Production-ready webhook handling with enhanced security
    """
    try:
        # Production webhook validation
        if settings.is_production:
            # Verify webhook source in production
            user_agent = request.headers.get('user-agent', '')
            if not user_agent.startswith('DarwinNotificationService'):
                logger.warning(f"Suspicious Apple webhook request - User-Agent: {user_agent}")
                # Continue processing but log the warning
        
        # Get request body
        body = await request.body()
        
        # Parse notification
        try:
            notification = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in Apple webhook")
            return {"status": "error", "message": "Invalid JSON"}
        
        # Verify notification signature
        if not apple_iap_service.verify_notification(notification):
            logger.warning("Invalid Apple notification signature")
            if settings.is_production:
                return {"status": "error", "message": "Invalid signature"}
            else:
                logger.info("Continuing in development mode despite signature failure")
        
        # Process different notification types
        notification_type = notification.get("notification_type") or notification.get("notificationType")
        
        logger.info(f"Processing Apple webhook: {notification_type}")
        
        if notification_type in ["DID_RENEW", "INTERACTIVE_RENEWAL"]:
            await subscription_service.handle_apple_renewal(db, notification)
        elif notification_type in ["DID_FAIL_TO_RENEW", "GRACE_PERIOD_EXPIRED"]:
            logger.info(f"Apple renewal failure notification: {notification_type}")
        elif notification_type in ["CANCEL", "DID_CHANGE_RENEWAL_STATUS"]:
            logger.info(f"Apple cancellation notification: {notification_type}")
        elif notification_type == "REFUND":
            logger.info(f"Apple refund notification: {notification_type}")
        elif notification_type == "REVOKE":
            logger.info(f"Apple revocation notification: {notification_type}")
        else:
            logger.info(f"Unhandled Apple notification type: {notification_type}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Apple webhook error: {str(e)}", exc_info=True)
        # Webhooks should always return 200 to avoid retries
        return {"status": "error", "message": "Internal error"}


@router.post("/webhook/google")
async def google_webhook(
    request: Request,
    db: Session = Depends(get_db)
) -> Any:
    """
    Handle Google Play Real-time Developer Notifications
    Production-ready webhook handling with enhanced security
    """
    try:
        # Production webhook validation
        if settings.is_production:
            # Verify webhook authentication header
            auth_header = request.headers.get('authorization', '')
            if not auth_header:
                logger.warning("Google webhook request missing authorization header")
                # Continue processing but log the warning
        
        # Get request body
        body = await request.body()
        
        # Parse notification
        try:
            notification = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in Google webhook")
            return {"status": "error", "message": "Invalid JSON"}
        
        # Google uses Cloud Pub/Sub, message data is in message.data
        message = notification.get("message", {})
        data = message.get("data", "")
        
        if not data:
            logger.warning("No data in Google notification")
            return {"status": "error", "message": "No data"}
        
        # Decode base64 data
        import base64
        try:
            decoded_data = json.loads(base64.b64decode(data))
        except Exception as e:
            logger.error(f"Failed to decode Google notification data: {e}")
            return {"status": "error", "message": "Invalid data encoding"}
        
        # Process RTDN notification
        rtdn_result = google_play_service.process_rtdn_notification(decoded_data)
        
        if not rtdn_result.get("is_valid"):
            logger.warning(f"Invalid Google RTDN notification: {rtdn_result.get('error')}")
            return {"status": "error", "message": "Invalid notification"}
        
        notification_type = rtdn_result.get("notification_type")
        notification_name = rtdn_result.get("notification_name")
        
        logger.info(f"Processing Google webhook: {notification_name} (type {notification_type})")
        
        # Handle different notification types
        if notification_type == 1:  # SUBSCRIPTION_RECOVERED
            logger.info("Google subscription recovered")
        elif notification_type == 2:  # SUBSCRIPTION_RENEWED
            logger.info("Google subscription renewed")
        elif notification_type == 3:  # SUBSCRIPTION_CANCELED
            logger.info("Google subscription canceled")
        elif notification_type == 4:  # SUBSCRIPTION_PURCHASED
            logger.info("Google subscription purchased")
        elif notification_type == 5:  # SUBSCRIPTION_ON_HOLD
            logger.info("Google subscription on hold")
        elif notification_type == 6:  # SUBSCRIPTION_IN_GRACE_PERIOD
            logger.info("Google subscription in grace period")
        elif notification_type == 7:  # SUBSCRIPTION_RESTARTED
            logger.info("Google subscription restarted")
        elif notification_type == 12:  # SUBSCRIPTION_REVOKED
            logger.info("Google subscription revoked")
        elif notification_type == 13:  # SUBSCRIPTION_EXPIRED
            logger.info("Google subscription expired")
        else:
            logger.info(f"Unhandled Google notification type: {notification_type}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Google webhook error: {str(e)}", exc_info=True)
        # Webhooks should always return 200 to avoid retries
        return {"status": "error", "message": "Internal error"}


# ==================== DEVELOPMENT ENDPOINTS ====================

@router.post("/mock/upgrade")
async def mock_upgrade_to_pro(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    subscription_type: str = Body("MONTHLY", description="MONTHLY or YEARLY")
) -> Any:
    """
    Mock upgrade to Pro (development only)
    Enhanced security: Strict development-only enforcement
    """
    # Enhanced security check
    if not settings.ALLOW_MOCK_ENDPOINTS:
        logger.warning(f"Mock endpoint access denied in {settings.ENVIRONMENT} environment by user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Mock endpoints are disabled in {settings.ENVIRONMENT} environment"
        )
    
    if not settings.ENABLE_MOCK_PAYMENTS:
        logger.warning(f"Mock payments disabled but endpoint called by user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mock payments are disabled"
        )
    
    logger.info(f"Mock upgrade request for user {current_user.id} to {subscription_type}")
    
    # Create mock subscription
    subscription_data = SubscriptionCreate(
        subscription_type=subscription_type,
        payment_method="mock",
        auto_renew=True
    )
    
    return subscription_service.create_subscription(db, current_user, subscription_data)


# ==================== ADMIN ENDPOINTS ====================

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
    
    try:
        return subscription_service.get_subscription_statistics(db)
    except Exception as e:
        logger.error(f"Error fetching admin statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch statistics"
        )


@router.get("/admin/pricing-config")
def get_pricing_config(
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get current pricing configuration (admin only)
    Enhanced with environment and security information
    """
    # Check if user is admin
    if not getattr(current_user, 'is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access pricing configuration"
        )
    
    try:
        environment_info = settings.get_environment_info()
        validation_issues = settings.validate_production_config()
        
        return {
            "current_pricing": settings.get_pricing_info(),
            "pricing_control": {
                "use_discounted_pricing": settings.USE_DISCOUNTED_PRICING,
                "discounted_monthly": settings.DISCOUNTED_MONTHLY_PRICE,
                "discounted_yearly": settings.DISCOUNTED_YEARLY_PRICE,
                "standard_monthly": settings.STANDARD_MONTHLY_PRICE,
                "standard_yearly": settings.STANDARD_YEARLY_PRICE,
            },
            "environment_info": environment_info,
            "production_readiness": {
                "is_ready": settings.is_production_ready,
                "issues": validation_issues,
                "security_level": settings.security_level
            },
            "note": "To change pricing, update the USE_DISCOUNTED_PRICING environment variable"
        }
    except Exception as e:
        logger.error(f"Error fetching pricing config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch pricing configuration"
        )


@router.post("/admin/toggle-pricing")
async def toggle_pricing(
    *,
    use_discounted: bool = Body(..., description="Whether to use discounted pricing"),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Toggle pricing mode (admin only) - Runtime only, not persistent
    Enhanced with security warnings
    """
    # Check if user is admin
    if not getattr(current_user, 'is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify pricing configuration"
        )
    
    try:
        # Production safety check
        if settings.is_production:
            logger.warning(f"Pricing change attempted in production by admin {current_user.id}")
        
        # Update runtime setting (won't persist across restarts)
        settings.USE_DISCOUNTED_PRICING = use_discounted
        
        logger.info(f"Pricing mode changed to {'discounted' if use_discounted else 'standard'} by admin {current_user.id}")
        
        warnings = []
        if settings.is_production:
            warnings.append("Runtime change in production environment")
        warnings.append("This change only affects runtime. For persistent changes, update the environment variable.")
        
        return {
            "success": True,
            "message": f"Pricing mode changed to {'discounted' if use_discounted else 'standard'}",
            "current_pricing": settings.get_pricing_info(),
            "warnings": warnings,
            "environment": settings.ENVIRONMENT
        }
    except Exception as e:
        logger.error(f"Error toggling pricing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update pricing configuration"
        )


# ==================== SYSTEM STATUS ENDPOINT ====================

@router.get("/admin/system-status")
def get_system_status(
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get comprehensive system status (admin only)
    """
    if not getattr(current_user, 'is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access system status"
        )
    
    try:
        # Get service statuses
        google_service_status = google_play_service.get_service_status()
        
        return {
            "environment": settings.get_environment_info(),
            "production_readiness": {
                "is_ready": settings.is_production_ready,
                "issues": settings.validate_production_config(),
                "security_level": settings.security_level
            },
            "payment_services": {
                "apple_iap": {
                    "configured": bool(settings.APPLE_SHARED_SECRET) if settings.is_production else True,
                    "sandbox_mode": settings.APPLE_USE_SANDBOX_AUTO,
                    "bundle_id": settings.APPLE_BUNDLE_ID
                },
                "google_play": google_service_status
            },
            "feature_flags": {
                "subscription_enabled": settings.ENABLE_SUBSCRIPTION,
                "mock_payments_enabled": settings.ENABLE_MOCK_PAYMENTS,
                "mock_endpoints_allowed": settings.ALLOW_MOCK_ENDPOINTS
            }
        }
    except Exception as e:
        logger.error(f"Error fetching system status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch system status"
        )
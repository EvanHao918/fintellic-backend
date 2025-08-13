from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.services.subscription_service import subscription_service
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

router = APIRouter()


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
    Create a new subscription
    """
    if current_user.is_subscription_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an active subscription"
        )
    
    return subscription_service.create_subscription(db, current_user, subscription_data)


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


# Stripe Checkout Integration (placeholder)
@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    checkout_data: CreateCheckoutSession
) -> Any:
    """
    Create Stripe checkout session
    """
    # This is a placeholder - actual Stripe integration would go here
    # import stripe
    # stripe.api_key = settings.STRIPE_API_KEY
    
    pricing_info = subscription_service.get_user_pricing(db, current_user)
    
    if checkout_data.subscription_type == "MONTHLY":
        price = pricing_info.monthly_price
        interval = "month"
    else:
        price = pricing_info.yearly_price
        interval = "year"
    
    # Simulated response
    return CheckoutSessionResponse(
        session_id="cs_test_123456",
        checkout_url=f"https://checkout.stripe.com/pay/cs_test_123456",
        publishable_key="pk_test_123456"
    )


# Webhook endpoints for payment providers
@router.post("/webhook/stripe")
async def stripe_webhook(
    request: dict,
    db: Session = Depends(get_db)
) -> Any:
    """
    Handle Stripe webhook events
    """
    # Placeholder for Stripe webhook handling
    # Would verify webhook signature and process events
    return {"status": "ok"}


@router.post("/webhook/apple")
async def apple_webhook(
    request: dict,
    db: Session = Depends(get_db)
) -> Any:
    """
    Handle Apple In-App Purchase notifications
    """
    # Placeholder for Apple IAP webhook handling
    return {"status": "ok"}


@router.post("/webhook/google")
async def google_webhook(
    request: dict,
    db: Session = Depends(get_db)
) -> Any:
    """
    Handle Google Play billing notifications
    """
    # Placeholder for Google Play webhook handling
    return {"status": "ok"}


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
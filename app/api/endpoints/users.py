from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from app.api.deps import get_db, get_current_active_user
from app.crud.user import crud_user
from app.models.user import User
from app.schemas.user import (
    UserResponse, 
    UserDetailResponse,
    UserUpdate, 
    UserUpdatePassword,
    SubscriptionInfo,
    PricingInfo
)
from app.core.security import verify_password, get_password_hash
from app.core.config import settings
from app.services.subscription_service import subscription_service
from fastapi import Body

router = APIRouter()


def _get_utc_now() -> datetime:
    """获取UTC时间，确保时区一致性"""
    return datetime.now(timezone.utc)


@router.get("/me", response_model=UserDetailResponse)
def read_user_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get current user profile with subscription details
    """
    # 获取用户的价格信息
    pricing_info = subscription_service.get_user_pricing(db, current_user)
    
    # 构建响应，包含订阅信息
    response = UserDetailResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        username=current_user.username,
        is_active=current_user.is_active,
        tier=current_user.tier,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
        is_verified=current_user.is_verified,
        daily_reports_count=current_user.daily_reports_count,
        
        # 订阅相关字段
        subscription_type=current_user.subscription_type,
        pricing_tier=current_user.pricing_tier,
        is_subscription_active=current_user.is_subscription_active,
        is_early_bird=current_user.is_early_bird,
        subscription_expires_at=current_user.subscription_expires_at,
        subscription_started_at=current_user.subscription_started_at,
        subscription_cancelled_at=current_user.subscription_cancelled_at,
        subscription_price=float(current_user.subscription_price) if current_user.subscription_price else None,
        next_billing_date=current_user.next_billing_date,
        subscription_auto_renew=current_user.subscription_auto_renew,
        
        # 价格信息
        monthly_price=pricing_info.monthly_price,
        yearly_price=pricing_info.yearly_price,
        
        # 支付历史
        last_payment_date=current_user.last_payment_date,
        last_payment_amount=float(current_user.last_payment_amount) if current_user.last_payment_amount else None,
        total_payment_amount=float(current_user.total_payment_amount) if current_user.total_payment_amount else 0,
        
        # 其他
        user_sequence_number=current_user.user_sequence_number,
        subscription_metadata=current_user.subscription_metadata,
        
        # 订阅状态
        subscription_status="active" if current_user.is_subscription_active else "inactive"
    )
    
    return response


@router.put("/me", response_model=UserResponse)
def update_user_me(
    *,
    db: Session = Depends(get_db),
    user_in: UserUpdate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Update current user profile
    """
    # Check if email is being changed and already exists
    if user_in.email and user_in.email != current_user.email:
        existing_user = crud_user.get_by_email(db, email=user_in.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email already exists"
            )
    
    # Check if username is being changed and already exists
    if user_in.username and user_in.username != current_user.username:
        existing_user = crud_user.get_by_username(db, username=user_in.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This username is already taken"
            )
    
    # Update user
    user = crud_user.update(db, db_obj=current_user, obj_in=user_in)
    
    # 获取价格信息用于响应
    pricing_info = subscription_service.get_user_pricing(db, user)
    
    # 构建响应
    response = UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        username=user.username,
        is_active=user.is_active,
        tier=user.tier,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        is_verified=user.is_verified,
        daily_reports_count=user.daily_reports_count,
        subscription_expires_at=user.subscription_expires_at,
        subscription_type=user.subscription_type,
        pricing_tier=user.pricing_tier,
        is_subscription_active=user.is_subscription_active,
        is_early_bird=user.is_early_bird,
        monthly_price=pricing_info.monthly_price,
        yearly_price=pricing_info.yearly_price,
        next_billing_date=user.next_billing_date,
        subscription_auto_renew=user.subscription_auto_renew,
        subscription_status="active" if user.is_subscription_active else "inactive"
    )
    
    return response


@router.put("/me/password", response_model=dict)
def update_password_me(
    *,
    db: Session = Depends(get_db),
    body: UserUpdatePassword,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Update current user password
    """
    # Verify current password
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password"
        )
    
    # Update password
    current_user.hashed_password = get_password_hash(body.new_password)
    db.add(current_user)
    db.commit()
    
    return {"message": "Password updated successfully"}


@router.get("/me/subscription", response_model=SubscriptionInfo)
def read_user_subscription(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get current user subscription status with detailed info
    """
    # 获取订阅信息
    subscription_info = subscription_service.get_current_subscription(db, current_user)
    return subscription_info


@router.get("/me/pricing", response_model=PricingInfo)
def read_user_pricing(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get personalized pricing for current user
    """
    # 获取价格信息
    pricing_info = subscription_service.get_user_pricing(db, current_user)
    return pricing_info


@router.delete("/me", response_model=dict)
def delete_user_me(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Delete current user account (soft delete)
    """
    # Cancel any active subscriptions first
    if current_user.is_subscription_active:
        from app.schemas.subscription import SubscriptionCancel
        cancel_data = SubscriptionCancel(
            reason="account_deletion",
            feedback="User deleted account"
        )
        subscription_service.cancel_subscription(db, current_user, cancel_data)
    
    # Soft delete user
    current_user.is_active = False
    db.add(current_user)
    db.commit()
    
    return {"message": "Account deactivated successfully"}


@router.post("/me/upgrade-mock", response_model=dict)
def mock_upgrade_to_pro(
    plan: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Mock endpoint to upgrade user to Pro (for development only)
    Note: This endpoint should be removed in production
    """
    if settings.ENVIRONMENT == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint not found"
        )
    
    if current_user.tier == "PRO":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already Pro"
        )
    
    try:
        # 🔥 修复：统一时区处理
        current_time = _get_utc_now()
        
        # 🔥 修复：基于序号判定早鸟状态和价格
        is_early_bird = current_user.user_sequence_number is not None and current_user.user_sequence_number <= settings.EARLY_BIRD_LIMIT
        
        if plan == "yearly":
            subscription_price = settings.EARLY_BIRD_YEARLY_PRICE if is_early_bird else settings.STANDARD_YEARLY_PRICE
            expires_at = current_time + timedelta(days=365)
            subscription_type = "YEARLY"
        else:
            subscription_price = settings.EARLY_BIRD_MONTHLY_PRICE if is_early_bird else settings.STANDARD_MONTHLY_PRICE
            expires_at = current_time + timedelta(days=30)
            subscription_type = "MONTHLY"
        
        # Mock upgrade - set Pro status
        current_user.tier = "PRO"
        current_user.is_subscription_active = True
        current_user.subscription_type = subscription_type
        current_user.subscription_started_at = current_time
        current_user.subscription_expires_at = expires_at
        current_user.next_billing_date = expires_at
        current_user.subscription_price = subscription_price
        current_user.subscription_auto_renew = True
        
        # 🔥 修复：确保早鸟状态和价格层级正确设置
        current_user.is_early_bird = is_early_bird
        current_user.pricing_tier = "EARLY_BIRD" if is_early_bird else "STANDARD"
        
        # 更新支付信息
        current_user.last_payment_date = current_time
        current_user.last_payment_amount = subscription_price
        current_user.total_payment_amount = (current_user.total_payment_amount or 0) + subscription_price
        current_user.payment_method = "mock"
        
        db.add(current_user)
        db.commit()
        db.refresh(current_user)
        
        # 🔥 修复：返回完整的用户信息，包括正确的monthly_price
        return {
            "message": f"Successfully upgraded to Pro ({plan}) - Mock",
            "user": {
                "id": current_user.id,
                "email": current_user.email,
                "username": current_user.username,
                "full_name": current_user.full_name,
                "is_pro": True,
                "tier": "PRO",
                "subscription_type": current_user.subscription_type,
                "subscription_expires_at": current_user.subscription_expires_at.isoformat() if current_user.subscription_expires_at else None,
                "is_early_bird": current_user.is_early_bird,
                "pricing_tier": current_user.pricing_tier,
                "subscription_price": float(current_user.subscription_price),
                "monthly_price": current_user.monthly_price,  # 这是@property，会动态计算
                "user_sequence_number": current_user.user_sequence_number,
                "is_subscription_active": current_user.is_subscription_active,
                "subscription_auto_renew": current_user.subscription_auto_renew,
                "payment_method": current_user.payment_method,
                "last_payment_date": current_user.last_payment_date.isoformat() if current_user.last_payment_date else None,
                "last_payment_amount": float(current_user.last_payment_amount) if current_user.last_payment_amount else None,
                "total_payment_amount": float(current_user.total_payment_amount) if current_user.total_payment_amount else 0,
            }
        }
        
    except Exception as e:
        logger.error(f"Error in mock upgrade for user {current_user.id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upgrade user: {str(e)}"
        )
from datetime import timedelta
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
import secrets
import json

from app.api.deps import get_db, get_current_user
from app.core.config import settings
from app.core.security import (
    create_access_token, 
    verify_password, 
    get_password_hash,
    verify_token
)
from app.crud.user import crud_user
from app.schemas.auth import (
    Token, 
    RegisterRequest, 
    RegisterResponse,
    RefreshTokenRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    PasswordResetResponse,
    SecurityInfoResponse,
    AuthErrorResponse
)
from app.schemas.user import UserCreate, UserDetailResponse
from app.models.user import User, PricingTier
from app.services.email_service import email_service

router = APIRouter()


def create_tokens(user_id: int, device_id: Optional[str] = None) -> dict:
    """Create access and refresh tokens"""
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    token_data = {"sub": str(user_id)}
    if device_id:
        token_data["device_id"] = device_id
        
    access_token = create_access_token(
        data=token_data, 
        expires_delta=access_token_expires
    )
    
    # Create refresh token (30 days)
    refresh_token_expires = timedelta(days=30)
    refresh_token = create_access_token(
        data={**token_data, "type": "refresh"},
        expires_delta=refresh_token_expires
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


def get_early_bird_stats(db: Session) -> dict:
    """获取早鸟统计信息"""
    early_bird_count = db.query(func.count(User.id)).filter(
        User.is_early_bird == True
    ).scalar()
    
    slots_remaining = max(0, settings.EARLY_BIRD_LIMIT - early_bird_count)
    
    return {
        "early_bird_users": early_bird_count,
        "early_bird_slots_remaining": slots_remaining,
        "is_early_bird_available": slots_remaining > 0
    }


@router.post("/register", response_model=RegisterResponse)
def register(
    *,
    db: Session = Depends(get_db),
    user_in: RegisterRequest
) -> Any:
    """
    Register new user with automatic early bird eligibility check
    """
    # Check if user already exists
    user = crud_user.get_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists"
        )
    
    # Check if username is taken (if provided)
    if user_in.username:
        existing_username = crud_user.get_by_username(db, username=user_in.username)
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This username is already taken"
            )
    
    # Create new user
    user_create = UserCreate(
        email=user_in.email,
        password=user_in.password,
        full_name=user_in.full_name,
        username=user_in.username,
        promo_code=user_in.promo_code if hasattr(user_in, 'promo_code') else None,
        referral_code=user_in.referral_code if hasattr(user_in, 'referral_code') else None,
        registration_source=user_in.registration_source or "email",
        registration_device_type=user_in.device_type or "web"
    )
    user = crud_user.create(db, obj_in=user_create)
    
    # Refresh user object
    db.refresh(user)
    
    # Create tokens
    tokens = create_tokens(user.id, user_in.device_id)
    
    # Build response
    response_data = {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "username": user.username,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "tier": user.tier,
        "is_early_bird": user.is_early_bird or False,
        "pricing_tier": user.pricing_tier,
        "user_sequence_number": user.user_sequence_number,
        "monthly_price": user.monthly_price,
        "yearly_price": user.yearly_price,
        "early_bird_slots_remaining": 0
    }
    
    return RegisterResponse(**response_data)


@router.post("/login", response_model=Token)
def login(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
    device_id: Optional[str] = None
) -> Any:
    """
    OAuth2 compatible token login with subscription info
    """
    # Authenticate user
    user = crud_user.authenticate(
        db, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif not crud_user.is_active(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    # Update last login
    crud_user.update_last_login(db, user=user)
    
    # Create access token
    tokens = create_tokens(user.id, device_id)
    
    # Add subscription info to response
    tokens["user_info"] = {
        "id": user.id,
        "email": user.email,
        "tier": user.tier.value,
        "is_early_bird": user.is_early_bird,
        "pricing_tier": user.pricing_tier.value if user.pricing_tier else None,
        "is_subscription_active": user.is_subscription_active,
        "subscription_expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None
    }
    
    return Token(**tokens)


@router.post("/login/access-token", response_model=Token)
def login_access_token(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login (alternative endpoint)
    """
    return login(db=db, form_data=form_data)


# ==================== PASSWORD RESET ENDPOINTS ====================

@router.post("/password/reset-request", response_model=PasswordResetResponse)
def request_password_reset(
    *,
    db: Session = Depends(get_db),
    reset_request: PasswordResetRequest
) -> Any:
    """
    Request password reset email
    """
    if not settings.ENABLE_PASSWORD_RESET:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Password reset is not enabled"
        )
    
    # Find user by email
    user = crud_user.get_by_email(db, email=reset_request.email)
    
    # Always return success for security (don't reveal if email exists)
    success_message = "If the email exists in our system, a password reset email has been sent."
    
    if not user:
        return PasswordResetResponse(
            message=success_message,
            success=True
        )
    
    # Check if user can request password reset (rate limiting)
    if not user.can_request_password_reset():
        if user.is_password_reset_locked():
            return PasswordResetResponse(
                message="Too many password reset attempts. Please try again later.",
                success=False,
                can_retry_after=user.password_reset_locked_until
            )
        else:
            return PasswordResetResponse(
                message="Please wait before requesting another password reset.",
                success=False
            )
    
    # Send password reset email
    try:
        email_sent = email_service.send_password_reset_email(user, db)
        if email_sent:
            return PasswordResetResponse(
                message=success_message,
                success=True
            )
        else:
            # Log error but don't reveal failure to user
            print(f"Failed to send password reset email to {user.email}")
            return PasswordResetResponse(
                message=success_message,
                success=True
            )
    except Exception as e:
        print(f"Error sending password reset email: {e}")
        return PasswordResetResponse(
            message=success_message,
            success=True
        )


@router.post("/password/reset-confirm", response_model=PasswordResetResponse)
def confirm_password_reset(
    *,
    db: Session = Depends(get_db),
    reset_confirm: PasswordResetConfirm
) -> Any:
    """
    Confirm password reset using token and set new password
    """
    if not settings.ENABLE_PASSWORD_RESET:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Password reset is not enabled"
        )
    
    # Find user by reset token
    user = db.query(User).filter(
        User.password_reset_token == reset_confirm.token
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Check if token is still valid
    if not user.is_password_reset_token_valid():
        user.clear_password_reset_data()
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired"
        )
    
    # Check if account is locked due to too many attempts
    if user.is_password_reset_locked():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account is temporarily locked. Please try again later."
        )
    
    try:
        # Set new password
        user.hashed_password = get_password_hash(reset_confirm.new_password)
        
        # Clear reset data
        user.clear_password_reset_data()
        
        # Update timestamps
        from datetime import datetime, timezone
        user.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        
        # Send password change notification
        try:
            email_service.send_password_changed_notification(user)
        except Exception as e:
            print(f"Failed to send password change notification: {e}")
        
        return PasswordResetResponse(
            message="Password reset successfully!",
            success=True
        )
        
    except Exception as e:
        db.rollback()
        user.increment_password_reset_attempts()
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset password"
        )

# ================================================================


# Refresh Token
@router.post("/refresh", response_model=Token)
async def refresh_token(
    *,
    db: Session = Depends(get_db),
    token_data: RefreshTokenRequest
) -> Any:
    """
    Refresh access token using refresh token
    """
    # Verify the refresh token
    payload = verify_token(token_data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    # Get user
    user = crud_user.get(db, id=int(user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new tokens
    tokens = create_tokens(user.id, payload.get("device_id"))
    
    # Add user info
    tokens["user_info"] = {
        "id": user.id,
        "email": user.email,
        "tier": user.tier.value,
        "is_early_bird": user.is_early_bird,
        "pricing_tier": user.pricing_tier.value if user.pricing_tier else None,
        "is_subscription_active": user.is_subscription_active,
        "subscription_expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None
    }
    
    return Token(**tokens)


# Security info endpoint
@router.get("/security-info", response_model=SecurityInfoResponse)
def get_security_info(
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get user security information
    """
    # Get social providers
    social_providers = []
    if current_user.apple_user_id:
        social_providers.append("apple")
    if current_user.google_user_id:
        social_providers.append("google")
    if current_user.linkedin_user_id:
        social_providers.append("linkedin")
    
    return SecurityInfoResponse(
        email_verified=current_user.is_verified,
        has_password=bool(current_user.hashed_password),
        social_providers=social_providers,
        biometric_enabled=bool(current_user.biometric_settings),
        last_login_at=current_user.last_login_at,
        is_account_locked=current_user.is_password_reset_locked()
    )


# New endpoint: Get early bird status
@router.get("/early-bird-status")
def get_early_bird_status(db: Session = Depends(get_db)) -> Any:
    """
    Get current early bird availability status
    """
    stats = get_early_bird_stats(db)
    
    return {
        "early_bird_limit": settings.EARLY_BIRD_LIMIT,
        "early_bird_users": stats["early_bird_users"],
        "slots_remaining": stats["early_bird_slots_remaining"],
        "is_available": stats["is_early_bird_available"],
        "early_bird_monthly_price": settings.EARLY_BIRD_MONTHLY_PRICE,
        "early_bird_yearly_price": settings.EARLY_BIRD_YEARLY_PRICE,
        "standard_monthly_price": settings.STANDARD_MONTHLY_PRICE,
        "standard_yearly_price": settings.STANDARD_YEARLY_PRICE
    }
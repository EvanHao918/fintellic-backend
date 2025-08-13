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
    AppleSignInRequest,
    GoogleSignInRequest,
    BiometricAuthRequest,
    RefreshTokenRequest
)
from app.schemas.user import UserCreate, UserDetailResponse
from app.models.user import User, PricingTier

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
    
    # Create new user (数据库触发器会自动设置user_sequence_number和早鸟状态)
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
    
    # 刷新用户对象以获取触发器设置的值
    db.refresh(user)
    
    # Create tokens
    tokens = create_tokens(user.id, user_in.device_id)
    
    # Get early bird stats
    early_bird_stats = get_early_bird_stats(db)
    
    # Build response with subscription info
    response_data = {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "username": user.username,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "tier": user.tier,
        "is_early_bird": user.is_early_bird,
        "pricing_tier": user.pricing_tier,
        "user_sequence_number": user.user_sequence_number,
        "monthly_price": user.monthly_price,
        "yearly_price": user.yearly_price,
        "early_bird_slots_remaining": early_bird_stats["early_bird_slots_remaining"]
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


# Apple Sign In
@router.post("/apple", response_model=Token)
async def apple_sign_in(
    *,
    db: Session = Depends(get_db),
    apple_data: AppleSignInRequest
) -> Any:
    """
    Apple Sign In authentication with early bird check
    """
    # In production, verify the identity token with Apple's servers
    # For now, we'll extract the email from the token payload
    # This is a simplified implementation
    
    email = apple_data.email
    apple_user_id = apple_data.user_id
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not provided by Apple"
        )
    
    # Check if user exists
    user = crud_user.get_by_email(db, email=email)
    
    if not user:
        # Create new user (触发器会自动设置早鸟状态)
        user_create = UserCreate(
            email=email,
            full_name=apple_data.full_name,
            password=secrets.token_urlsafe(32),  # Random password for social users
            registration_source="apple",
            registration_device_type="ios",
            apple_user_id=apple_user_id
        )
        user = crud_user.create(db, obj_in=user_create)
        db.refresh(user)  # 刷新以获取触发器设置的值
    else:
        # Update Apple user ID if not set
        if not user.apple_user_id:
            user.apple_user_id = apple_user_id
            db.commit()
    
    # Create tokens
    tokens = create_tokens(user.id, apple_data.device_id)
    
    # Add user info
    tokens["user_info"] = {
        "id": user.id,
        "email": user.email,
        "tier": user.tier.value,
        "is_early_bird": user.is_early_bird,
        "pricing_tier": user.pricing_tier.value if user.pricing_tier else None,
        "is_subscription_active": user.is_subscription_active
    }
    
    return Token(**tokens)


# Google Sign In
@router.post("/google", response_model=Token)
async def google_sign_in(
    *,
    db: Session = Depends(get_db),
    google_data: GoogleSignInRequest
) -> Any:
    """
    Google Sign In authentication with early bird check
    """
    # In production, verify the ID token with Google's servers
    # For now, we'll trust the provided data
    
    email = google_data.email
    google_user_id = google_data.user_id
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not provided by Google"
        )
    
    # Check if user exists
    user = crud_user.get_by_email(db, email=email)
    
    if not user:
        # Create new user (触发器会自动设置早鸟状态)
        user_create = UserCreate(
            email=email,
            full_name=google_data.full_name,
            password=secrets.token_urlsafe(32),  # Random password for social users
            avatar_url=google_data.photo_url,
            registration_source="google",
            registration_device_type="android",
            google_user_id=google_user_id
        )
        user = crud_user.create(db, obj_in=user_create)
        db.refresh(user)  # 刷新以获取触发器设置的值
    else:
        # Update Google user ID if not set
        if not user.google_user_id:
            user.google_user_id = google_user_id
            db.commit()
    
    # Create tokens
    tokens = create_tokens(user.id, google_data.device_id)
    
    # Add user info
    tokens["user_info"] = {
        "id": user.id,
        "email": user.email,
        "tier": user.tier.value,
        "is_early_bird": user.is_early_bird,
        "pricing_tier": user.pricing_tier.value if user.pricing_tier else None,
        "is_subscription_active": user.is_subscription_active
    }
    
    return Token(**tokens)


# Biometric Authentication
@router.post("/biometric", response_model=Token)
async def biometric_auth(
    *,
    db: Session = Depends(get_db),
    biometric_data: BiometricAuthRequest
) -> Any:
    """
    Biometric authentication (Face ID/Touch ID/Fingerprint)
    """
    # Verify the refresh token
    payload = verify_token(biometric_data.refresh_token)
    if not payload:
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
    
    # In production, you would verify the biometric data
    # For now, we trust the client's biometric verification
    
    # Create new tokens
    tokens = create_tokens(user.id, biometric_data.device_id)
    
    # Add user info
    tokens["user_info"] = {
        "id": user.id,
        "email": user.email,
        "tier": user.tier.value,
        "is_early_bird": user.is_early_bird,
        "pricing_tier": user.pricing_tier.value if user.pricing_tier else None,
        "is_subscription_active": user.is_subscription_active
    }
    
    return Token(**tokens)


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
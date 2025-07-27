from datetime import timedelta
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
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
from app.schemas.user import UserCreate
from app.models.user import User

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


@router.post("/register", response_model=RegisterResponse)
def register(
    *,
    db: Session = Depends(get_db),
    user_in: RegisterRequest
) -> Any:
    """
    Register new user
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
        registration_source=user_in.registration_source or "email",
        registration_device_type=user_in.device_type or "web"
    )
    user = crud_user.create(db, obj_in=user_create)
    
    # Create tokens
    tokens = create_tokens(user.id, user_in.device_id)
    
    return RegisterResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        username=user.username,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"]
    )


@router.post("/login", response_model=Token)
def login(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
    device_id: Optional[str] = None
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
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
    Apple Sign In authentication
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
        # Create new user
        user_create = UserCreate(
            email=email,
            full_name=apple_data.full_name,
            password=secrets.token_urlsafe(32),  # Random password for social users
            registration_source="apple",
            registration_device_type="ios",
            apple_user_id=apple_user_id
        )
        user = crud_user.create(db, obj_in=user_create)
    else:
        # Update Apple user ID if not set
        if not user.apple_user_id:
            user.apple_user_id = apple_user_id
            db.commit()
    
    # Create tokens
    tokens = create_tokens(user.id, apple_data.device_id)
    
    return Token(**tokens)


# Google Sign In
@router.post("/google", response_model=Token)
async def google_sign_in(
    *,
    db: Session = Depends(get_db),
    google_data: GoogleSignInRequest
) -> Any:
    """
    Google Sign In authentication
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
        # Create new user
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
    else:
        # Update Google user ID if not set
        if not user.google_user_id:
            user.google_user_id = google_user_id
            db.commit()
    
    # Create tokens
    tokens = create_tokens(user.id, google_data.device_id)
    
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
    
    return Token(**tokens)
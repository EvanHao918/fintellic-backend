from typing import Optional
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_token
from app.models.user import User

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# OAuth2 scheme for optional token authentication
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False  # This makes the token optional
)


async def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """
    Get current authenticated user from JWT token
    
    Args:
        db: Database session
        token: JWT token from Authorization header
        
    Returns:
        Current user object
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Verify and decode token
    payload = verify_token(token)
    if payload is None:
        raise credentials_exception
    
    # Extract user_id from token
    user_id: int = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current active user
    
    Args:
        current_user: User from get_current_user dependency
        
    Returns:
        Active user object
        
    Raises:
        HTTPException: If user is not active
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


async def get_current_pro_user(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current user with active Pro subscription
    
    Args:
        current_user: Active user from get_current_active_user
        db: Database session for checking subscription status
        
    Returns:
        Pro user object
        
    Raises:
        HTTPException: If user is not Pro tier or subscription expired
    """
    # Check if user has PRO tier
    if current_user.tier != "PRO":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pro subscription required"
        )
    
    # Check if subscription is active
    if not current_user.is_subscription_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pro subscription is not active"
        )
    
    # Check if subscription is still valid
    if current_user.subscription_expires_at:
        if current_user.subscription_expires_at < datetime.utcnow():
            # Update user status if subscription expired
            current_user.tier = "FREE"
            current_user.is_subscription_active = False
            db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Pro subscription expired. Please renew your subscription."
            )
    
    return current_user


async def check_daily_limit(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Check if free user has reached daily report limit
    
    Args:
        current_user: Active user
        db: Database session
        
    Returns:
        User object if limit not reached
        
    Raises:
        HTTPException: If daily limit reached
    """
    # Pro users have unlimited access
    if current_user.tier == "PRO" and current_user.is_subscription_active:
        return current_user
    
    # Check if daily limit needs reset
    if current_user.daily_reports_reset_at:
        if current_user.daily_reports_reset_at < datetime.utcnow():
            current_user.daily_reports_count = 0
            current_user.daily_reports_reset_at = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
            db.commit()
    else:
        # Set initial reset time
        current_user.daily_reports_reset_at = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        db.commit()
    
    # Check daily limit
    if current_user.daily_reports_count >= settings.FREE_USER_DAILY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Daily limit of {settings.FREE_USER_DAILY_LIMIT} reports reached. Upgrade to Pro for unlimited access.",
            headers={
                "X-Daily-Limit": str(settings.FREE_USER_DAILY_LIMIT),
                "X-Reports-Used": str(current_user.daily_reports_count),
                "X-Reset-Time": current_user.daily_reports_reset_at.isoformat()
            }
        )
    
    return current_user


async def get_current_user_optional(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme_optional)
) -> Optional[User]:
    """
    Get current user if authenticated, otherwise return None
    
    Used for endpoints that have different behavior for authenticated vs anonymous users
    
    Args:
        db: Database session
        token: Optional JWT token from Authorization header
        
    Returns:
        Current user object or None
    """
    if not token:
        return None
    
    try:
        # Verify and decode token
        payload = verify_token(token)
        if payload is None:
            return None
        
        # Extract user_id from token
        user_id: int = payload.get("sub")
        if user_id is None:
            return None
        
        # Get user from database
        user = db.query(User).filter(User.id == user_id).first()
        if user is None or not user.is_active:
            return None
        
        return user
    except:
        # If any error occurs, treat as anonymous user
        return None


async def get_subscription_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Get user with active subscription (alias for get_current_pro_user)
    Used for endpoints that require an active subscription
    
    Args:
        current_user: Active user
        
    Returns:
        User with active subscription
        
    Raises:
        HTTPException: If user doesn't have active subscription
    """
    if not current_user.is_subscription_active:
        # Provide helpful information about subscription status
        if current_user.is_early_bird:
            message = "Subscription required. As an early bird user, you can get special pricing!"
        else:
            message = "Subscription required. Upgrade to Pro for unlimited access."
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
            headers={
                "X-Subscription-Required": "true",
                "X-Is-Early-Bird": str(current_user.is_early_bird).lower(),
                "X-Pricing-Tier": current_user.pricing_tier or "STANDARD"
            }
        )
    
    return current_user


async def check_subscription_validity(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Check if user's subscription is still valid and update status if expired
    
    Args:
        current_user: Active user
        db: Database session
        
    Returns:
        User object with updated subscription status
    """
    if current_user.is_subscription_active and current_user.subscription_expires_at:
        if current_user.subscription_expires_at < datetime.utcnow():
            # Subscription has expired
            current_user.tier = "FREE"
            current_user.is_subscription_active = False
            current_user.subscription_type = None
            
            # Log the expiration
            if current_user.subscription_metadata is None:
                current_user.subscription_metadata = {}
            current_user.subscription_metadata["last_expired_at"] = datetime.utcnow().isoformat()
            
            db.commit()
    
    return current_user
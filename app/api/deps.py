from typing import Optional
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_token
from app.models.user import User, UserTier

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


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
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Get current user with Pro subscription
    
    Args:
        current_user: Active user from get_current_active_user
        
    Returns:
        Pro user object
        
    Raises:
        HTTPException: If user is not Pro tier
    """
    if current_user.tier != UserTier.PRO:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pro subscription required"
        )
    
    # Check if subscription is still valid
    if current_user.subscription_expires_at:
        if current_user.subscription_expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Pro subscription expired"
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
    if current_user.tier == UserTier.PRO:
        return current_user
    
    # Check if daily limit needs reset
    if current_user.daily_reports_reset_at:
        if current_user.daily_reports_reset_at < datetime.utcnow():
            current_user.daily_reports_count = 0
            current_user.daily_reports_reset_at = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
            db.commit()
    
    # Check daily limit
    if current_user.daily_reports_count >= settings.FREE_USER_DAILY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Daily limit of {settings.FREE_USER_DAILY_LIMIT} reports reached. Upgrade to Pro for unlimited access."
        )
    
    return current_user
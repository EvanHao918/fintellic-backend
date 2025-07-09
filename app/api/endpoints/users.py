from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_active_user
from app.crud.user import crud_user
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate, UserUpdatePassword
from app.core.security import verify_password, get_password_hash
from datetime import datetime, timedelta
from fastapi import Body

router = APIRouter()


@router.get("/me", response_model=UserResponse)
def read_user_me(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get current user profile
    """
    return current_user


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
    return user


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


@router.get("/me/subscription", response_model=dict)
def read_user_subscription(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get current user subscription status
    """
    is_pro = crud_user.is_pro(current_user)
    
    response = {
        "tier": current_user.tier,
        "is_pro": is_pro,
        "daily_reports_used": current_user.daily_reports_count,
        "daily_reports_limit": 3 if current_user.tier == "free" else None
    }
    
    if current_user.subscription_expires_at:
        response["expires_at"] = current_user.subscription_expires_at
    
    return response


@router.delete("/me", response_model=dict)
def delete_user_me(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Delete current user account (soft delete)
    """
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
    Mock endpoint to upgrade user to Pro (for development)
    """
    if current_user.tier == "pro":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already Pro"
        )
    
    # Mock upgrade - set Pro status
    current_user.tier = "pro"
    current_user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
    
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    
    return {
        "message": "Successfully upgraded to Pro (Mock)",
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "username": current_user.username,
            "full_name": current_user.full_name,
            "is_pro": True,
            "tier": "pro",
            "subscription_expires_at": current_user.subscription_expires_at.isoformat()
        }
    }
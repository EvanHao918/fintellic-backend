"""
Notification API Endpoints
Phase 4: HermeSpeed Push Notification System
FIXED: Test notification history recording regardless of Firebase configuration
"""
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from sqlalchemy.exc import ProgrammingError
from datetime import datetime, time

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.models.notification_settings import UserNotificationSettings, NotificationHistory
from app.schemas.notification import (
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
    DeviceTokenRegister,
    DeviceTokenUnregister,
    NotificationHistoryResponse,
    TestNotificationRequest
)
from app.core.config import settings
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/settings", response_model=NotificationSettingsResponse)
def get_notification_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get current user's notification settings
    """
    try:
        settings = db.query(UserNotificationSettings).filter_by(
            user_id=current_user.id
        ).first()
        
        if not settings:
            # Create default settings if not exists - SIMPLIFIED: Core features only
            settings = UserNotificationSettings(
                user_id=current_user.id,
                notification_enabled=True,
                filing_10k=True,
                filing_10q=True,
                filing_8k=True,
                filing_s1=True,
                watchlist_only=False
            )
            db.add(settings)
            db.commit()
            db.refresh(settings)
        
        return settings
    except Exception as e:
        logger.error(f"Error fetching notification settings for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch notification settings"
        )


@router.put("/settings", response_model=NotificationSettingsResponse)
def update_notification_settings(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    settings_in: NotificationSettingsUpdate
) -> Any:
    """
    Update notification settings - SIMPLIFIED: Core filing preferences only
    """
    try:
        settings = db.query(UserNotificationSettings).filter_by(
            user_id=current_user.id
        ).first()
        
        if not settings:
            # Create with provided settings - SIMPLIFIED: Only core fields
            settings = UserNotificationSettings(
                user_id=current_user.id,
                notification_enabled=settings_in.notification_enabled if settings_in.notification_enabled is not None else True,
                filing_10k=settings_in.filing_10k if settings_in.filing_10k is not None else True,
                filing_10q=settings_in.filing_10q if settings_in.filing_10q is not None else True,
                filing_8k=settings_in.filing_8k if settings_in.filing_8k is not None else True,
                filing_s1=settings_in.filing_s1 if settings_in.filing_s1 is not None else True,
                watchlist_only=settings_in.watchlist_only if settings_in.watchlist_only is not None else False
            )
            db.add(settings)
        else:
            # Update existing settings - SIMPLIFIED: Only allow core fields
            core_fields = ['notification_enabled', 'filing_10k', 'filing_10q', 'filing_8k', 'filing_s1', 'watchlist_only']
            update_data = settings_in.dict(exclude_unset=True, include=set(core_fields))
            for field, value in update_data.items():
                setattr(settings, field, value)
        
        db.commit()
        db.refresh(settings)
        
        logger.info(f"Updated notification settings for user {current_user.id}: {settings_in.dict(exclude_unset=True)}")
        return settings
    except Exception as e:
        logger.error(f"Error updating notification settings for user {current_user.id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update notification settings"
        )


@router.post("/device/register", response_model=dict)
def register_device_token(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    token_data: DeviceTokenRegister
) -> Any:
    """
    Register a device token for push notifications
    FIXED: Unified token storage in users table only
    """
    try:
        # UNIFIED: Store tokens only in users table
        if not current_user.device_tokens:
            current_user.device_tokens = "[]"
        
        tokens = json.loads(current_user.device_tokens) if current_user.device_tokens else []
        
        # Check if token already exists
        token_exists = False
        for device in tokens:
            if device.get('token') == token_data.token:
                # Update timestamp and platform
                device['updated_at'] = datetime.utcnow().isoformat()
                device['platform'] = token_data.platform
                token_exists = True
                break
        
        if not token_exists:
            # Add new token
            tokens.append({
                'token': token_data.token,
                'platform': token_data.platform,
                'added_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            })
        
        # UNIFIED: Save to users table only
        current_user.device_tokens = json.dumps(tokens)
        db.commit()
        
        logger.info(f"Registered device token for user {current_user.id} (platform: {token_data.platform})")
        
        return {
            "success": True,
            "message": "Device token registered successfully"
        }
        
    except Exception as e:
        logger.error(f"Error registering device token for user {current_user.id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register device token"
        )


@router.post("/device/unregister", response_model=dict)
def unregister_device_token(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    token_data: DeviceTokenUnregister
) -> Any:
    """
    Unregister a device token
    FIXED: Unified token storage in users table only
    """
    try:
        if current_user.device_tokens:
            tokens = json.loads(current_user.device_tokens)
            # Remove specified token
            tokens = [d for d in tokens if d.get('token') != token_data.token]
            current_user.device_tokens = json.dumps(tokens)
            db.commit()
        
        logger.info(f"Unregistered device token for user {current_user.id}")
        
        return {
            "success": True,
            "message": "Device token unregistered successfully"
        }
        
    except Exception as e:
        logger.error(f"Error unregistering device token for user {current_user.id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unregister device token"
        )


@router.get("/history", response_model=List[NotificationHistoryResponse])
def get_notification_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: int = 0,
    limit: int = 50
) -> Any:
    """
    Get notification history for current user
    FIXED: Proper error handling instead of silent failure
    """
    try:
        history = db.query(NotificationHistory).filter_by(
            user_id=current_user.id
        ).order_by(
            NotificationHistory.created_at.desc()
        ).offset(skip).limit(limit).all()
        
        return history
    except ProgrammingError as pe:
        logger.error(f"Database permission error accessing notification_history for user {current_user.id}: {pe}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notification history service temporarily unavailable"
        )
    except Exception as e:
        logger.error(f"Error fetching notification history for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch notification history"
        )


@router.post("/test", response_model=dict)
def send_test_notification(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    test_data: TestNotificationRequest = None
) -> Any:
    """
    Send a test notification
    FIXED: Always create history record regardless of Firebase configuration
    """
    try:
        logger.info(f"Test notification request for user {current_user.id}")
        
        # Prepare notification content
        title = (test_data and test_data.title) or "HermeSpeed Test"
        body = (test_data and test_data.body) or f"Test notification sent at {datetime.utcnow().strftime('%H:%M:%S UTC')}"
        
        # Check Firebase configuration
        firebase_configured = False
        try:
            import firebase_admin
            if firebase_admin._apps:
                firebase_configured = True
                logger.info("Firebase is configured and initialized")
        except ImportError:
            logger.warning("Firebase admin not installed")
        except Exception as e:
            logger.warning(f"Firebase check failed: {e}")
        
        # FIXED: Always create history record first
        history = NotificationHistory(
            user_id=current_user.id,
            notification_type='test',
            title=title,
            body=body,
            status='pending',  # Start as pending
            sent_at=None      # Will be updated if successful
        )
        db.add(history)
        db.flush()  # Get the ID without committing yet
        
        # If Firebase not configured, update status and return
        if not firebase_configured:
            logger.info("Firebase not configured, returning clear message to user")
            history.status = 'failed'
            history.error_message = "Push notification service is not configured"
            db.commit()
            
            return {
                "success": False,
                "message": "Push notification service is not configured. Please contact support.",
                "firebase_configured": False
            }
        
        # Firebase is configured - proceed with real test
        if not current_user.device_tokens:
            history.status = 'failed'
            history.error_message = "No device tokens registered"
            db.commit()
            
            return {
                "success": False,
                "message": "No device tokens registered. Please enable notifications in app settings."
            }
        
        tokens = json.loads(current_user.device_tokens) if current_user.device_tokens else []
        token_list = [d['token'] for d in tokens if d.get('token')]
        
        if not token_list:
            history.status = 'failed'
            history.error_message = "No valid device tokens found"
            db.commit()
            
            return {
                "success": False,
                "message": "No valid device tokens found. Please restart the app and try again."
            }
        
        # Send test notification via Firebase
        try:
            from firebase_admin import messaging
            
            message = messaging.MulticastMessage(
                tokens=token_list,
                notification=messaging.Notification(title=title, body=body),
                data={'type': 'test', 'timestamp': datetime.utcnow().isoformat()}
            )
            
            response = messaging.send_multicast(message)
            
            # Update history based on result
            if response.success_count > 0:
                history.status = 'sent'
                history.sent_at = datetime.utcnow()
            else:
                history.status = 'failed'
                history.error_message = f"Firebase failed to send to all devices"
            
            db.commit()
            
            return {
                "success": True,
                "message": f"Test notification sent to {response.success_count} device(s)",
                "firebase_configured": True,
                "success_count": response.success_count,
                "failure_count": response.failure_count
            }
            
        except Exception as firebase_error:
            logger.error(f"Firebase send error: {firebase_error}")
            history.status = 'failed'
            history.error_message = str(firebase_error)
            db.commit()
            
            return {
                "success": False,
                "message": f"Firebase send failed: {str(firebase_error)}"
            }
        
    except Exception as e:
        logger.error(f"Error in test notification for user {current_user.id}: {str(e)}")
        
        # Try to update history if it exists
        try:
            if 'history' in locals():
                history.status = 'failed'
                history.error_message = str(e)
                db.commit()
        except:
            pass
        
        return {
            "success": False,
            "message": f"Test notification failed: {str(e)}"
        }


@router.get("/stats", response_model=dict)
def get_notification_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get notification statistics for current user
    SIMPLIFIED: Basic stats only, improved error handling
    """
    try:
        # Get device count from unified storage
        device_count = 0
        if current_user.device_tokens:
            try:
                tokens = json.loads(current_user.device_tokens)
                device_count = len(tokens)
            except:
                pass
        
        # Get notification settings
        notification_settings = db.query(UserNotificationSettings).filter_by(
            user_id=current_user.id
        ).first()
        
        settings_enabled = notification_settings.notification_enabled if notification_settings else False
        
        # SIMPLIFIED: Basic stats without complex history queries
        try:
            total_sent = db.query(NotificationHistory).filter_by(
                user_id=current_user.id,
                status='sent'
            ).count()
            
            total_failed = db.query(NotificationHistory).filter_by(
                user_id=current_user.id,
                status='failed'
            ).count()
            
        except Exception as history_error:
            logger.warning(f"Error accessing notification history for stats: {history_error}")
            total_sent = 0
            total_failed = 0
        
        return {
            "total_sent": total_sent,
            "total_failed": total_failed,
            "device_count": device_count,
            "settings": {
                "enabled": settings_enabled,
                "watchlist_only": notification_settings.watchlist_only if notification_settings else False
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching notification stats for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch notification statistics"
        )
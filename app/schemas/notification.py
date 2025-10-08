"""
Notification Schemas
Phase 4: HermeSpeed Push Notification System
OPTIMIZED: Simplified schemas matching core functionality only
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, time
from pydantic import BaseModel, Field


class NotificationSettingsBase(BaseModel):
    """
    Base notification settings schema
    SIMPLIFIED: Core filing preferences only
    """
    # Core filing type notifications
    filing_10k: bool = True
    filing_10q: bool = True
    filing_8k: bool = True
    filing_s1: bool = True
    
    # Notification scope
    watchlist_only: bool = False
    
    # Master switch
    notification_enabled: bool = True


class NotificationSettingsUpdate(BaseModel):
    """
    Schema for updating notification settings
    SIMPLIFIED: Only core fields allowed
    """
    filing_10k: Optional[bool] = None
    filing_10q: Optional[bool] = None
    filing_8k: Optional[bool] = None
    filing_s1: Optional[bool] = None
    watchlist_only: Optional[bool] = None
    notification_enabled: Optional[bool] = None


class NotificationSettingsResponse(NotificationSettingsBase):
    """
    Response schema for notification settings
    SIMPLIFIED: Core fields only with metadata
    """
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class DeviceTokenRegister(BaseModel):
    """Schema for registering a device token"""
    token: str = Field(..., min_length=1, description="FCM device token")
    platform: Optional[str] = Field(None, description="Platform: ios, android")


class DeviceTokenUnregister(BaseModel):
    """Schema for unregistering a device token"""
    token: str = Field(..., min_length=1, description="FCM device token to remove")


class NotificationHistoryResponse(BaseModel):
    """
    Response schema for notification history
    SIMPLIFIED: Core tracking fields only
    """
    id: int
    notification_type: str
    title: str
    body: str
    data: Optional[Dict[str, Any]] = None
    status: str
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class TestNotificationRequest(BaseModel):
    """Request schema for sending test notification"""
    title: Optional[str] = Field(None, description="Notification title")
    body: Optional[str] = Field(None, description="Notification body")


class NotificationStatsResponse(BaseModel):
    """
    Response schema for notification statistics
    SIMPLIFIED: Essential stats only
    """
    total_sent: int
    total_failed: int
    device_count: int
    settings: Dict[str, Any]


# SIMPLIFIED: Core notification preferences for UI
NOTIFICATION_LABELS = {
    'filing_10k': 'Annual Reports (10-K)',
    'filing_10q': 'Quarterly Reports (10-Q)',
    'filing_8k': 'Current Reports (8-K)',
    'filing_s1': 'IPO Filings (S-1)',
    'watchlist_only': 'Watchlist Only',
    'notification_enabled': 'Push Notifications',
}


NOTIFICATION_DESCRIPTIONS = {
    'filing_10k': 'Get notified when companies file their annual reports',
    'filing_10q': 'Get notified when companies file quarterly reports',
    'filing_8k': 'Get notified about significant events and changes',
    'filing_s1': 'Get notified when companies file for IPO',
    'watchlist_only': 'Only receive notifications for companies in your watchlist',
    'notification_enabled': 'Master switch for all push notifications',
}


# Default notification settings for new users
DEFAULT_NOTIFICATION_SETTINGS = {
    'filing_10k': True,
    'filing_10q': True,
    'filing_8k': True,
    'filing_s1': True,
    'watchlist_only': False,
    'notification_enabled': True,
}
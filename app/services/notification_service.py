"""
Firebase Cloud Messaging Notification Service
Phase 4: HermeSpeed Push Notification System
OPTIMIZED: Simplified Firebase initialization, unified token management, core features only
UPDATED: Added Expo Push API support for Expo tokens
"""
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, time
import json
import os
from pathlib import Path
import requests

import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models.user import User
from app.models.notification_settings import UserNotificationSettings, NotificationHistory
from app.models.filing import Filing
from app.models.watchlist import Watchlist
from app.core.config import settings

logger = logging.getLogger(__name__)

# Expo Push API endpoint
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class NotificationService:
    """
    Firebase notification service
    OPTIMIZED: Simplified initialization, core features only, unified token management
    UPDATED: Supports both FCM tokens and Expo Push Tokens
    """
    
    def __init__(self):
        self.initialized = False
        self.app = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """
        SIMPLIFIED: Cleaner Firebase initialization with better error handling
        """
        try:
            # Check if already initialized
            if firebase_admin._apps:
                self.app = firebase_admin.get_app()
                self.initialized = True
                logger.info("Firebase already initialized")
                return
            
            # Method 1: Environment JSON key (production)
            if hasattr(settings, 'FIREBASE_SERVICE_ACCOUNT_KEY') and settings.FIREBASE_SERVICE_ACCOUNT_KEY:
                try:
                    cred_dict = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_KEY)
                    cred = credentials.Certificate(cred_dict)
                    self.app = firebase_admin.initialize_app(cred)
                    self.initialized = True
                    logger.info("Firebase initialized with environment JSON key")
                    return
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"Failed to initialize with environment JSON key: {e}")
            
            # Method 2: File path (development)
            if hasattr(settings, 'FIREBASE_SERVICE_ACCOUNT_PATH') and settings.FIREBASE_SERVICE_ACCOUNT_PATH:
                cred_path = Path(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
                if cred_path.exists() and cred_path.is_file():
                    try:
                        cred = credentials.Certificate(str(cred_path))
                        self.app = firebase_admin.initialize_app(cred)
                        self.initialized = True
                        logger.info(f"Firebase initialized with credential file: {cred_path}")
                        return
                    except Exception as e:
                        logger.warning(f"Failed to initialize with credential file: {e}")
            
            # Not configured - this is OK for development
            logger.info("Firebase credentials not configured - push notifications will be simulated")
            self.initialized = False
            
        except Exception as e:
            logger.error(f"Firebase initialization failed: {e}")
            self.initialized = False
    
    def is_firebase_ready(self) -> bool:
        """Check if Firebase is ready"""
        return self.initialized and self.app is not None
    
    def _is_expo_token(self, token: str) -> bool:
        """Check if token is an Expo Push Token"""
        return token.startswith('ExponentPushToken[') or token.startswith('ExpoPushToken[')
    
    def _send_expo_notifications(self, tokens: List[str], title: str, body: str, data: Dict) -> Dict[str, Any]:
        """
        Send notifications via Expo Push API
        Returns dict with success_count and failure_count
        """
        if not tokens:
            return {"success_count": 0, "failure_count": 0, "responses": []}
        
        # Build Expo push messages
        messages = []
        for token in tokens:
            messages.append({
                "to": token,
                "sound": "default",
                "title": title,
                "body": body,
                "data": data,
                "priority": "high",
                "channelId": "default"
            })
        
        try:
            response = requests.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                    "Content-Type": "application/json"
                },
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            data_list = result.get("data", [])
            
            success_count = 0
            failure_count = 0
            responses = []
            
            for item in data_list:
                if item.get("status") == "ok":
                    success_count += 1
                    responses.append({"success": True})
                else:
                    failure_count += 1
                    responses.append({
                        "success": False, 
                        "error": item.get("message", "Unknown error")
                    })
            
            logger.info(f"Expo push result: {success_count} success, {failure_count} failed")
            return {
                "success_count": success_count,
                "failure_count": failure_count,
                "responses": responses
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Expo push request failed: {e}")
            return {
                "success_count": 0,
                "failure_count": len(tokens),
                "responses": [{"success": False, "error": str(e)} for _ in tokens]
            }
    
    def send_filing_notification(
        self, 
        db: Session, 
        filing: Filing,
        notification_type: str = "filing_release"
    ) -> int:
        """
        Send filing release notification for core filing types only
        OPTIMIZED: Simplified content generation, unified token retrieval
        UPDATED: Deduplicate by device token to avoid duplicate notifications on same device
        """
        # For Expo tokens, we don't need Firebase to be ready
        # if not self.is_firebase_ready():
        #     logger.warning("Firebase not ready - skipping filing notification")
        #     return 0
        
        try:
            # Build notification content - SIMPLIFIED
            company_name = filing.company.name
            ticker = filing.company.ticker
            filing_type = filing.filing_type.value if hasattr(filing.filing_type, 'value') else str(filing.filing_type)
            
            # Handle None ticker for IPO companies - use company name abbreviation or "IPO"
            display_ticker = ticker if ticker else (company_name.split()[0][:6].upper() if company_name else "IPO")
            
            # SIMPLIFIED: Core filing types only
            title_map = {
                '10-K': f"📊 {display_ticker} Annual Report Filed",
                '10-Q': f"📈 {display_ticker} Quarterly Report Filed",
                '8-K': f"📢 {display_ticker} Major Event Filed",
                'S-1': f"🚀 {display_ticker} IPO Filing Submitted"
            }
            
            body_map = {
                '10-K': f"{company_name} published their latest annual report",
                '10-Q': f"{company_name} published their latest quarterly earnings",
                '8-K': f"{company_name} filed a major event disclosure",
                'S-1': f"{company_name} submitted IPO registration documents"
            }
            
            title = title_map.get(filing_type, f"📰 {display_ticker} Filed {filing_type}")
            
            # Use AI-generated summary as notification body if available
            # This gives users a preview of the actual content, creating natural interest
            default_body = body_map.get(filing_type, f"{company_name} published new SEC filing")
            
            if filing.unified_feed_summary:
                body = filing.unified_feed_summary
            else:
                body = default_body
            
            # Get users who need notification
            users_to_notify = self._get_users_for_filing_notification(db, filing)
            
            if not users_to_notify:
                logger.info(f"No users to notify for filing {filing.id}")
                return 0
            
            # OPTIMIZATION: Deduplicate by device token
            # Collect all tokens and map them to one user (first user found with that token)
            token_to_user = {}  # token -> user
            for user in users_to_notify:
                tokens = self._get_user_device_tokens(user)
                for token in tokens:
                    if token not in token_to_user:
                        token_to_user[token] = user
            
            logger.info(f"Deduplication: {len(users_to_notify)} users -> {len(token_to_user)} unique device tokens")
            
            # Group tokens back by user (use first user for each unique token)
            unique_users_with_tokens = {}  # user_id -> (user, [tokens])
            for token, user in token_to_user.items():
                if user.id not in unique_users_with_tokens:
                    unique_users_with_tokens[user.id] = (user, [])
                unique_users_with_tokens[user.id][1].append(token)
            
            # Send notifications (one per unique device)
            success_count = 0
            notification_data = {
                'filing_id': str(filing.id),
                'ticker': display_ticker,
                'filing_type': filing_type,
                'company_id': str(filing.company_id)
            }
            
            for user_id, (user, tokens) in unique_users_with_tokens.items():
                try:
                    notifications_sent = self._send_notification_to_tokens(
                        db=db,
                        user=user,
                        tokens=tokens,
                        title=title,
                        body=body,
                        notification_type=notification_type,
                        data=notification_data
                    )
                    success_count += notifications_sent
                    
                except Exception as user_error:
                    logger.error(f"Failed to send notification to user {user.id}: {user_error}")
                    continue
            
            db.commit()
            logger.info(f"Successfully sent {success_count} notifications for filing {filing.id}")
            return success_count
            
        except Exception as e:
            logger.error(f"Error sending filing notification: {e}")
            return 0
    
    def _send_notification_to_tokens(
        self,
        db: Session,
        user: User,
        tokens: List[str],
        title: str,
        body: str,
        notification_type: str,
        data: Dict
    ) -> int:
        """
        Send notification to specific tokens (used for deduplicated sending)
        """
        try:
            # Separate Expo tokens and FCM tokens
            expo_tokens = [t for t in tokens if self._is_expo_token(t)]
            fcm_tokens = [t for t in tokens if not self._is_expo_token(t)]
            
            total_success = 0
            notification_data = {
                **data,
                'type': notification_type,
                'click_action': 'FLUTTER_NOTIFICATION_CLICK',
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Send via Expo Push API for Expo tokens
            if expo_tokens:
                expo_result = self._send_expo_notifications(
                    tokens=expo_tokens,
                    title=title,
                    body=body,
                    data=notification_data
                )
                total_success += expo_result["success_count"]
                
                # Record history for Expo notifications
                if expo_result["success_count"] > 0:
                    self._record_notification_history_simple(
                        db=db,
                        user_id=user.id,
                        notification_type=notification_type,
                        title=title,
                        body=body,
                        data=data,
                        success_count=expo_result["success_count"]
                    )
                
                logger.info(f"Expo notification to user {user.id}: {expo_result['success_count']} success, {expo_result['failure_count']} failed")
            
            # Send via FCM for Firebase tokens (only if Firebase is ready)
            if fcm_tokens and self.is_firebase_ready():
                # Build and send message
                message = messaging.MulticastMessage(
                    tokens=fcm_tokens,
                    notification=messaging.Notification(title=title, body=body),
                    data={k: str(v) for k, v in notification_data.items()},
                    android=messaging.AndroidConfig(
                        priority='high',
                        notification=messaging.AndroidNotification(
                            icon=getattr(settings, 'NOTIFICATION_DEFAULT_ICON', 'ic_notification'),
                            color=getattr(settings, 'NOTIFICATION_DEFAULT_COLOR', '#E88B00'),
                            sound=getattr(settings, 'NOTIFICATION_DEFAULT_SOUND', 'default'),
                            channel_id='hermespeed_filings'
                        ),
                    ),
                    apns=messaging.APNSConfig(
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(
                                alert=messaging.ApsAlert(title=title, body=body),
                                sound='default',
                                badge=1,
                            )
                        )
                    ),
                )
                
                response = messaging.send_multicast(message)
                total_success += response.success_count
                
                # Record history
                self._record_notification_history(
                    db=db,
                    user_id=user.id,
                    notification_type=notification_type,
                    title=title,
                    body=body,
                    data=data,
                    tokens=fcm_tokens,
                    response=response
                )
                
                # Handle failed tokens
                if response.failure_count > 0:
                    self._handle_failed_tokens(db, user, fcm_tokens, response)
                
                logger.info(f"FCM notification to user {user.id}: {response.success_count} success, {response.failure_count} failed")
            
            return total_success
            
        except Exception as e:
            logger.error(f"Error sending notification to tokens: {e}")
            return 0
    
    def _send_notification_to_user(
        self,
        db: Session,
        user: User, 
        title: str,
        body: str,
        notification_type: str,
        data: Dict
    ) -> int:
        """
        Send notification to a single user
        OPTIMIZED: Unified token retrieval from users table only
        UPDATED: Supports both Expo and FCM tokens
        """
        try:
            # Get user's notification settings
            user_settings = db.query(UserNotificationSettings).filter_by(user_id=user.id).first()
            
            if not user_settings or not user_settings.notification_enabled:
                return 0
            
            # UNIFIED: Get device tokens from users table only
            tokens = self._get_user_device_tokens(user)
            if not tokens:
                logger.debug(f"User {user.id} has no active tokens")
                return 0
            
            # Separate Expo tokens and FCM tokens
            expo_tokens = [t for t in tokens if self._is_expo_token(t)]
            fcm_tokens = [t for t in tokens if not self._is_expo_token(t)]
            
            total_success = 0
            notification_data = {
                **data,
                'type': notification_type,
                'click_action': 'FLUTTER_NOTIFICATION_CLICK',
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Send via Expo Push API for Expo tokens
            if expo_tokens:
                expo_result = self._send_expo_notifications(
                    tokens=expo_tokens,
                    title=title,
                    body=body,
                    data=notification_data
                )
                total_success += expo_result["success_count"]
                
                # Record history for Expo notifications
                if expo_result["success_count"] > 0:
                    self._record_notification_history_simple(
                        db=db,
                        user_id=user.id,
                        notification_type=notification_type,
                        title=title,
                        body=body,
                        data=data,
                        success_count=expo_result["success_count"]
                    )
                
                logger.info(f"Expo notification to user {user.id}: {expo_result['success_count']} success, {expo_result['failure_count']} failed")
            
            # Send via FCM for Firebase tokens (only if Firebase is ready)
            if fcm_tokens and self.is_firebase_ready():
                # Build and send message
                message = messaging.MulticastMessage(
                    tokens=fcm_tokens,
                    notification=messaging.Notification(title=title, body=body),
                    data={k: str(v) for k, v in notification_data.items()},  # FCM requires string values
                    android=messaging.AndroidConfig(
                        priority='high',
                        notification=messaging.AndroidNotification(
                            icon=getattr(settings, 'NOTIFICATION_DEFAULT_ICON', 'ic_notification'),
                            color=getattr(settings, 'NOTIFICATION_DEFAULT_COLOR', '#E88B00'),
                            sound=getattr(settings, 'NOTIFICATION_DEFAULT_SOUND', 'default'),
                            channel_id='hermespeed_filings'
                        ),
                    ),
                    apns=messaging.APNSConfig(
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(
                                alert=messaging.ApsAlert(title=title, body=body),
                                sound='default',
                                badge=1,
                            )
                        )
                    ),
                )
                
                # Send multicast message
                response = messaging.send_multicast(message)
                total_success += response.success_count
                
                # Record history
                self._record_notification_history(
                    db=db,
                    user_id=user.id,
                    notification_type=notification_type,
                    title=title,
                    body=body,
                    data=data,
                    tokens=fcm_tokens,
                    response=response
                )
                
                # Handle failed tokens
                if response.failure_count > 0:
                    self._handle_failed_tokens(db, user, fcm_tokens, response)
                
                logger.info(f"FCM notification to user {user.id}: {response.success_count} success, {response.failure_count} failed")
            
            return total_success
            
        except Exception as e:
            logger.error(f"Error sending notification to user {user.id}: {e}")
            return 0
    
    def _get_user_device_tokens(self, user: User) -> List[str]:
        """
        UNIFIED: Get device tokens from users table only
        """
        try:
            if not user.device_tokens:
                return []
            
            tokens_data = json.loads(user.device_tokens)
            return [d.get('token') for d in tokens_data if d.get('token')]
        except Exception as e:
            logger.warning(f"Error parsing device tokens for user {user.id}: {e}")
            return []
    
    def _record_notification_history_simple(
        self,
        db: Session,
        user_id: int,
        notification_type: str,
        title: str,
        body: str,
        data: Dict,
        success_count: int
    ):
        """Record notification history for Expo notifications"""
        try:
            if success_count > 0:
                history = NotificationHistory(
                    user_id=user_id,
                    notification_type=notification_type,
                    title=title,
                    body=body,
                    data=data,
                    status='sent',
                    sent_at=datetime.utcnow()
                )
                db.add(history)
                
        except Exception as e:
            logger.warning(f"Error recording notification history: {e}")
    
    def _record_notification_history(
        self,
        db: Session,
        user_id: int,
        notification_type: str,
        title: str,
        body: str,
        data: Dict,
        tokens: List[str],
        response: messaging.BatchResponse
    ):
        """Record notification history with error handling"""
        try:
            # Create single history record for successful notifications
            if response.success_count > 0:
                history = NotificationHistory(
                    user_id=user_id,
                    notification_type=notification_type,
                    title=title,
                    body=body,
                    data=data,
                    status='sent',
                    sent_at=datetime.utcnow()
                )
                db.add(history)
                
        except Exception as e:
            logger.warning(f"Error recording notification history: {e}")
            # Don't fail the notification if history recording fails
    
    def _handle_failed_tokens(
        self,
        db: Session,
        user: User,
        tokens: List[str],
        response: messaging.BatchResponse
    ):
        """
        Handle failed device tokens
        OPTIMIZED: Clean invalid tokens from unified storage
        """
        try:
            if not user.device_tokens:
                return
                
            tokens_data = json.loads(user.device_tokens)
            tokens_to_remove = []
            
            for i, resp in enumerate(response.responses):
                if not resp.success and i < len(tokens):
                    error_code = str(resp.exception) if resp.exception else ""
                    
                    # Remove invalid tokens
                    if any(invalid_code in error_code.lower() for invalid_code in [
                        'registration-token-not-registered',
                        'invalid-registration-token',
                        'not-registered'
                    ]):
                        tokens_to_remove.append(tokens[i])
            
            # Update user's device tokens
            if tokens_to_remove:
                updated_tokens = [
                    d for d in tokens_data 
                    if d.get('token') not in tokens_to_remove
                ]
                user.device_tokens = json.dumps(updated_tokens)
                db.commit()
                logger.info(f"Removed {len(tokens_to_remove)} invalid tokens for user {user.id}")
                        
        except Exception as e:
            logger.error(f"Error handling failed tokens: {e}")
    
    def _get_users_for_filing_notification(self, db: Session, filing: Filing) -> List[User]:
        """
        Get list of users who should receive filing notifications
        OPTIMIZED: Core filing types only, improved query performance
        """
        filing_type = filing.filing_type.value if hasattr(filing.filing_type, 'value') else str(filing.filing_type)
        company_id = filing.company_id
        
        # SIMPLIFIED: Core filing types only
        filing_type_field_map = {
            '10-K': UserNotificationSettings.filing_10k,
            '10-Q': UserNotificationSettings.filing_10q,
            '8-K': UserNotificationSettings.filing_8k,
            'S-1': UserNotificationSettings.filing_s1,
        }
        
        filing_field = filing_type_field_map.get(filing_type)
        if not filing_field:
            logger.warning(f"Unknown filing type for notifications: {filing_type}")
            return []
        
        # Query users who enabled this notification type
        base_query = db.query(User).join(
            UserNotificationSettings,
            User.id == UserNotificationSettings.user_id
        ).filter(
            and_(
                UserNotificationSettings.notification_enabled == True,
                filing_field == True,
            )
        )
        
        # Handle watchlist_only and all users
        watchlist_users = base_query.filter(
            UserNotificationSettings.watchlist_only == True
        ).join(
            Watchlist,
            and_(
                Watchlist.user_id == User.id,
                Watchlist.company_id == company_id
            )
        ).all()
        
        all_users = base_query.filter(
            UserNotificationSettings.watchlist_only == False
        ).all()
        
        # Merge and deduplicate
        unique_users = {user.id: user for user in watchlist_users + all_users}
        
        logger.info(f"Found {len(unique_users)} users for {filing_type} notification (company: {filing.company.ticker})")
        return list(unique_users.values())
    
    def send_test_notification(
        self,
        db: Session,
        user: User,
        title: str = "HermeSpeed Test",
        body: str = None
    ) -> Dict[str, Any]:
        """
        Send test notification
        SIMPLIFIED: Clean test notification logic
        UPDATED: Supports Expo tokens
        """
        if not body:
            body = f"Test notification sent at {datetime.utcnow().strftime('%H:%M:%S UTC')}"
        
        try:
            # Check if user has any tokens
            tokens = self._get_user_device_tokens(user)
            if not tokens:
                return {
                    "success": False,
                    "message": "No active device tokens found",
                    "firebase_configured": self.is_firebase_ready()
                }
            
            # Send real test notification
            notifications_sent = self._send_notification_to_user(
                db=db,
                user=user,
                title=title,
                body=body,
                notification_type='test',
                data={'type': 'test', 'timestamp': datetime.utcnow().isoformat()}
            )
            
            if notifications_sent > 0:
                db.commit()
                return {
                    "success": True,
                    "message": f"Test notification sent successfully",
                    "firebase_configured": True,
                    "notifications_sent": notifications_sent
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to send notification",
                    "firebase_configured": self.is_firebase_ready()
                }
                
        except Exception as e:
            logger.error(f"Error sending test notification: {e}")
            return {
                "success": False,
                "message": f"Test notification failed: {str(e)}",
                "firebase_configured": self.is_firebase_ready()
            }


# Create singleton instance
notification_service = NotificationService()
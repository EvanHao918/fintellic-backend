"""
Google Play Billing Service
Production-ready Google Play subscription verification and management
Phase 2: Removed all mock logic, production-ready implementation
"""
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings

logger = logging.getLogger(__name__)


class GooglePlayService:
    """Production-ready Google Play Service"""
    
    def __init__(self):
        """Initialize Google Play service with production configuration"""
        self.package_name = settings.GOOGLE_PACKAGE_NAME
        self.service = None
        self._initialize_service()
    
    def _initialize_service(self):
        """Initialize Google Play API service"""
        try:
            # Get service account credentials
            credentials = self._get_credentials()
            if credentials:
                # Build service
                self.service = build(
                    'androidpublisher', 
                    'v3', 
                    credentials=credentials,
                    cache_discovery=False
                )
                logger.info("Google Play service initialized successfully")
            else:
                if settings.is_production:
                    logger.error("Google Play service not initialized - missing credentials in production")
                else:
                    logger.warning("Google Play service not initialized - no credentials (development mode)")
                
        except Exception as e:
            logger.error(f"Failed to initialize Google Play service: {str(e)}")
            self.service = None
    
    def _get_credentials(self):
        """Get Google service account credentials"""
        try:
            # Method 1: From file path
            if settings.GOOGLE_SERVICE_ACCOUNT_KEY_PATH:
                logger.info(f"Loading Google credentials from file: {settings.GOOGLE_SERVICE_ACCOUNT_KEY_PATH}")
                return service_account.Credentials.from_service_account_file(
                    settings.GOOGLE_SERVICE_ACCOUNT_KEY_PATH,
                    scopes=['https://www.googleapis.com/auth/androidpublisher']
                )
            
            # Method 2: From base64 encoded JSON
            if settings.GOOGLE_SERVICE_ACCOUNT_KEY_BASE64:
                logger.info("Loading Google credentials from base64 encoded JSON")
                key_json = base64.b64decode(settings.GOOGLE_SERVICE_ACCOUNT_KEY_BASE64)
                key_dict = json.loads(key_json)
                return service_account.Credentials.from_service_account_info(
                    key_dict,
                    scopes=['https://www.googleapis.com/auth/androidpublisher']
                )
            
            # Method 3: From JSON string
            if settings.GOOGLE_SERVICE_ACCOUNT_KEY_JSON:
                logger.info("Loading Google credentials from JSON string")
                key_dict = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_KEY_JSON)
                return service_account.Credentials.from_service_account_info(
                    key_dict,
                    scopes=['https://www.googleapis.com/auth/androidpublisher']
                )
            
            # No credentials configured
            if settings.is_production:
                logger.error("No Google service account credentials configured for production")
            else:
                logger.info("No Google service account credentials configured for development")
            return None
            
        except Exception as e:
            logger.error(f"Error loading Google credentials: {str(e)}")
            return None
    
    async def verify_subscription(
        self,
        product_id: str,
        purchase_token: str
    ) -> Dict[str, Any]:
        """
        Verify Google Play subscription with production-ready error handling
        
        Args:
            product_id: Product ID (subscription ID)
            purchase_token: Purchase token
            
        Returns:
            Verification result dictionary
        """
        if not product_id or not purchase_token:
            return {
                "is_valid": False,
                "error": "Product ID and purchase token are required"
            }
        
        try:
            # Check if service is available
            if not self.service:
                error_msg = "Google Play service not initialized"
                if settings.is_production:
                    logger.error(f"{error_msg} - this will cause verification failures")
                return {
                    "is_valid": False,
                    "error": error_msg
                }
            
            # Validate product ID
            if not self._validate_product_id(product_id):
                logger.warning(f"Invalid product ID: {product_id}")
                return {
                    "is_valid": False,
                    "error": "Invalid product ID"
                }
            
            logger.info(f"Verifying Google subscription: {product_id}")
            
            # Call Google API to verify subscription
            result = self.service.purchases().subscriptions().get(
                packageName=self.package_name,
                subscriptionId=product_id,
                token=purchase_token
            ).execute()
            
            # Process verification result
            processed = self._process_verification_result(result, product_id)
            
            # Auto-acknowledge if subscription is valid and active but not acknowledged
            if processed.get("is_valid") and processed.get("is_active"):
                if result.get("acknowledgementState", 0) == 0:
                    await self.acknowledge_subscription(product_id, purchase_token)
                    processed["acknowledgement_state"] = 1  # Update local state
            
            return processed
            
        except HttpError as e:
            error_content = e.content.decode('utf-8') if e.content else str(e)
            logger.error(f"Google Play API error: {e.resp.status} - {error_content}")
            
            # Handle specific error codes
            if e.resp.status == 404:
                return {
                    "is_valid": False,
                    "error": "Subscription not found"
                }
            elif e.resp.status == 401:
                return {
                    "is_valid": False,
                    "error": "Authentication failed"
                }
            elif e.resp.status == 403:
                return {
                    "is_valid": False,
                    "error": "Permission denied"
                }
            else:
                return {
                    "is_valid": False,
                    "error": f"API error: {e.resp.status}"
                }
        except Exception as e:
            logger.error(f"Google Play verification unexpected error: {str(e)}")
            return {
                "is_valid": False,
                "error": "Verification failed"
            }
    
    def _process_verification_result(
        self, 
        result: Dict[str, Any],
        product_id: str
    ) -> Dict[str, Any]:
        """
        Process Google verification result with comprehensive validation
        
        Args:
            result: Google API response
            product_id: Product ID
            
        Returns:
            Processed verification result
        """
        # Check payment state
        # paymentState: 0 = Payment pending, 1 = Payment received, 2 = Free trial, 3 = Pending deferred upgrade/downgrade
        payment_state = result.get("paymentState", 0)
        
        # Check acknowledgement state
        # acknowledgementState: 0 = Yet to be acknowledged, 1 = Acknowledged
        acknowledgement_state = result.get("acknowledgementState", 0)
        
        # Check cancel reason
        # cancelReason: 0 = User canceled, 1 = System canceled (billing error), 2 = Replaced, 3 = Developer canceled
        cancel_reason = result.get("cancelReason")
        
        # Parse timestamps (milliseconds)
        start_time_ms = result.get("startTimeMillis")
        expiry_time_ms = result.get("expiryTimeMillis")
        
        start_time = None
        expiry_time = None
        is_active = False
        
        if start_time_ms:
            try:
                start_time = datetime.fromtimestamp(int(start_time_ms) / 1000)
            except (ValueError, TypeError, OSError) as e:
                logger.warning(f"Failed to parse startTimeMillis: {start_time_ms}, error: {e}")
        
        if expiry_time_ms:
            try:
                expiry_time = datetime.fromtimestamp(int(expiry_time_ms) / 1000)
                # Subscription is active if not expired and payment received or in trial
                is_active = expiry_time > datetime.now() and payment_state in [1, 2]
            except (ValueError, TypeError, OSError) as e:
                logger.warning(f"Failed to parse expiryTimeMillis: {expiry_time_ms}, error: {e}")
        
        # Check if auto-renewing
        auto_renewing = result.get("autoRenewing", False)
        
        # Determine subscription type
        subscription_type = self._get_subscription_type(product_id)
        
        # Get price information
        price_amount = None
        currency = result.get("priceCurrencyCode", "USD")
        
        if result.get("priceAmountMicros"):
            try:
                # Price is stored in micros (1 USD = 1,000,000 micros)
                price_amount = int(result.get("priceAmountMicros")) / 1000000
            except (ValueError, TypeError):
                logger.warning(f"Failed to parse priceAmountMicros: {result.get('priceAmountMicros')}")
        
        # Fallback to system configuration if no price from API
        if not price_amount:
            if subscription_type == "YEARLY":
                price_amount = settings.current_yearly_price
            else:
                price_amount = settings.current_monthly_price
        
        # Get user cancellation time
        user_cancellation_time_ms = result.get("userCancellationTimeMillis")
        cancelled_at = None
        if user_cancellation_time_ms:
            try:
                cancelled_at = datetime.fromtimestamp(int(user_cancellation_time_ms) / 1000).isoformat()
            except (ValueError, TypeError, OSError):
                cancelled_at = None
        
        # Check if in grace period (payment failed but still active)
        is_in_grace_period = expiry_time and expiry_time > datetime.now() and payment_state == 0
        
        return {
            "is_valid": True,
            "is_active": is_active,
            "product_id": product_id,
            "order_id": result.get("orderId"),
            "purchase_token": result.get("purchaseToken"),
            "subscription_type": subscription_type,
            "start_time": start_time.isoformat() if start_time else None,
            "expiry_time": expiry_time.isoformat() if expiry_time else None,
            "auto_renewing": auto_renewing,
            "payment_state": payment_state,
            "acknowledgement_state": acknowledgement_state,
            "is_trial": payment_state == 2,
            "is_in_grace_period": is_in_grace_period,
            "cancel_reason": cancel_reason,
            "cancelled_at": cancelled_at,
            "price": price_amount,
            "currency": currency,
            "country_code": result.get("countryCode"),
            "developer_payload": result.get("developerPayload"),
            "linked_purchase_token": result.get("linkedPurchaseToken"),  # For upgrades/downgrades
            "environment": "production",  # Always production for real Google Play
            "raw_response": result
        }
    
    async def acknowledge_subscription(
        self,
        product_id: str,
        purchase_token: str
    ) -> bool:
        """
        Acknowledge subscription (Google requires acknowledgment within 3 days)
        
        Args:
            product_id: Product ID
            purchase_token: Purchase token
            
        Returns:
            Whether successful
        """
        try:
            if not self.service:
                logger.error("Google Play service not available for acknowledgment")
                return False
            
            logger.info(f"Acknowledging Google subscription: {product_id}")
            
            self.service.purchases().subscriptions().acknowledge(
                packageName=self.package_name,
                subscriptionId=product_id,
                token=purchase_token,
                body={}
            ).execute()
            
            logger.info(f"Successfully acknowledged subscription: {product_id}")
            return True
            
        except HttpError as e:
            if e.resp.status == 400:
                # Might already be acknowledged
                logger.info(f"Subscription may already be acknowledged: {product_id}")
                return True
            logger.error(f"Failed to acknowledge subscription: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to acknowledge subscription: {str(e)}")
            return False
    
    async def cancel_subscription(
        self,
        product_id: str,
        purchase_token: str
    ) -> bool:
        """
        Cancel subscription
        
        Args:
            product_id: Product ID
            purchase_token: Purchase token
            
        Returns:
            Whether successful
        """
        try:
            if not self.service:
                logger.error("Google Play service not available for cancellation")
                return False
            
            logger.info(f"Cancelling Google subscription: {product_id}")
            
            self.service.purchases().subscriptions().cancel(
                packageName=self.package_name,
                subscriptionId=product_id,
                token=purchase_token
            ).execute()
            
            logger.info(f"Successfully cancelled subscription: {product_id}")
            return True
            
        except HttpError as e:
            logger.error(f"Failed to cancel subscription: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to cancel subscription: {str(e)}")
            return False
    
    async def defer_subscription(
        self,
        product_id: str,
        purchase_token: str,
        desired_expiry_time_ms: int
    ) -> bool:
        """
        Defer subscription expiry
        
        Args:
            product_id: Product ID
            purchase_token: Purchase token
            desired_expiry_time_ms: Desired expiry time in milliseconds
            
        Returns:
            Whether successful
        """
        try:
            if not self.service:
                logger.error("Google Play service not available for deferral")
                return False
            
            logger.info(f"Deferring Google subscription: {product_id}")
            
            self.service.purchases().subscriptions().defer(
                packageName=self.package_name,
                subscriptionId=product_id,
                token=purchase_token,
                body={
                    "deferralInfo": {
                        "desiredExpiryTimeMillis": str(desired_expiry_time_ms)
                    }
                }
            ).execute()
            
            logger.info(f"Successfully deferred subscription: {product_id}")
            return True
            
        except HttpError as e:
            logger.error(f"Failed to defer subscription: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to defer subscription: {str(e)}")
            return False
    
    def _get_subscription_type(self, product_id: str) -> str:
        """Determine subscription type from product ID"""
        if not product_id:
            return "MONTHLY"
        
        product_id_lower = product_id.lower()
        if "yearly" in product_id_lower or "annual" in product_id_lower:
            return "YEARLY"
        return "MONTHLY"
    
    def _validate_product_id(self, product_id: str) -> bool:
        """
        Validate if product ID is one of our configured products
        
        Args:
            product_id: Product ID to validate
            
        Returns:
            Whether product ID is valid
        """
        valid_product_ids = [
            settings.GOOGLE_MONTHLY_PRODUCT_ID,
            settings.GOOGLE_YEARLY_PRODUCT_ID
        ]
        return product_id in valid_product_ids
    
    def process_rtdn_notification(self, notification_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process Google Real-time Developer Notification
        
        Args:
            notification_data: Notification data
            
        Returns:
            Processing result
        """
        try:
            subscription_notification = notification_data.get("subscriptionNotification", {})
            
            notification_type = subscription_notification.get("notificationType")
            product_id = subscription_notification.get("subscriptionId")
            purchase_token = subscription_notification.get("purchaseToken")
            
            # Notification types mapping
            notification_type_names = {
                1: "SUBSCRIPTION_RECOVERED",
                2: "SUBSCRIPTION_RENEWED",
                3: "SUBSCRIPTION_CANCELED",
                4: "SUBSCRIPTION_PURCHASED",
                5: "SUBSCRIPTION_ON_HOLD",
                6: "SUBSCRIPTION_IN_GRACE_PERIOD",
                7: "SUBSCRIPTION_RESTARTED",
                8: "SUBSCRIPTION_PRICE_CHANGE_CONFIRMED",
                9: "SUBSCRIPTION_DEFERRED",
                10: "SUBSCRIPTION_PAUSED",
                11: "SUBSCRIPTION_PAUSE_SCHEDULE_CHANGED",
                12: "SUBSCRIPTION_REVOKED",
                13: "SUBSCRIPTION_EXPIRED"
            }
            
            notification_name = notification_type_names.get(notification_type, "UNKNOWN")
            
            # Validate product ID
            if product_id and not self._validate_product_id(product_id):
                logger.warning(f"RTDN notification for invalid product ID: {product_id}")
                return {
                    "is_valid": False,
                    "error": "Invalid product ID"
                }
            
            logger.info(f"Processing Google RTDN: {notification_name} for product: {product_id}")
            
            return {
                "notification_type": notification_type,
                "notification_name": notification_name,
                "product_id": product_id,
                "purchase_token": purchase_token,
                "is_valid": True
            }
            
        except Exception as e:
            logger.error(f"Error processing RTDN: {str(e)}")
            return {
                "is_valid": False,
                "error": str(e)
            }
    
    def get_service_status(self) -> Dict[str, Any]:
        """
        Get service initialization status
        
        Returns:
            Service status information
        """
        return {
            "service_initialized": self.service is not None,
            "package_name": self.package_name,
            "environment": settings.ENVIRONMENT,
            "credentials_configured": bool(
                settings.GOOGLE_SERVICE_ACCOUNT_KEY_PATH or 
                settings.GOOGLE_SERVICE_ACCOUNT_KEY_BASE64 or 
                settings.GOOGLE_SERVICE_ACCOUNT_KEY_JSON
            )
        }


# Create service instance
google_play_service = GooglePlayService()
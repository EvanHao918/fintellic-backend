"""
Google Play Billing Service
处理Google Play订阅验证和管理
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
    """Google Play服务类"""
    
    def __init__(self):
        """初始化服务"""
        self.package_name = settings.GOOGLE_PACKAGE_NAME if hasattr(settings, 'GOOGLE_PACKAGE_NAME') else "com.hermespeed.app"
        self.service = None
        self._initialize_service()
    
    def _initialize_service(self):
        """初始化Google Play API服务"""
        try:
            # 获取服务账号凭证
            credentials = self._get_credentials()
            if credentials:
                # 构建服务
                self.service = build(
                    'androidpublisher', 
                    'v3', 
                    credentials=credentials,
                    cache_discovery=False
                )
                logger.info("Google Play service initialized successfully")
            else:
                logger.warning("Google Play service not initialized - no credentials")
                
        except Exception as e:
            logger.error(f"Failed to initialize Google Play service: {str(e)}")
            self.service = None
    
    def _get_credentials(self):
        """获取Google服务账号凭证"""
        try:
            # 方式1：从文件路径读取
            if hasattr(settings, 'GOOGLE_SERVICE_ACCOUNT_KEY_PATH') and settings.GOOGLE_SERVICE_ACCOUNT_KEY_PATH:
                logger.info(f"Loading Google credentials from file: {settings.GOOGLE_SERVICE_ACCOUNT_KEY_PATH}")
                return service_account.Credentials.from_service_account_file(
                    settings.GOOGLE_SERVICE_ACCOUNT_KEY_PATH,
                    scopes=['https://www.googleapis.com/auth/androidpublisher']
                )
            
            # 方式2：从base64编码的JSON读取
            if hasattr(settings, 'GOOGLE_SERVICE_ACCOUNT_KEY_BASE64') and settings.GOOGLE_SERVICE_ACCOUNT_KEY_BASE64:
                logger.info("Loading Google credentials from base64 encoded JSON")
                key_json = base64.b64decode(settings.GOOGLE_SERVICE_ACCOUNT_KEY_BASE64)
                key_dict = json.loads(key_json)
                return service_account.Credentials.from_service_account_info(
                    key_dict,
                    scopes=['https://www.googleapis.com/auth/androidpublisher']
                )
            
            # 方式3：从JSON字符串读取
            if hasattr(settings, 'GOOGLE_SERVICE_ACCOUNT_KEY_JSON') and settings.GOOGLE_SERVICE_ACCOUNT_KEY_JSON:
                logger.info("Loading Google credentials from JSON string")
                key_dict = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_KEY_JSON)
                return service_account.Credentials.from_service_account_info(
                    key_dict,
                    scopes=['https://www.googleapis.com/auth/androidpublisher']
                )
            
            # 开发环境返回None
            if settings.ENVIRONMENT == "development":
                logger.info("Development environment - using mock Google service")
                return None
                
            logger.warning("No Google service account credentials configured")
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
        验证Google Play订阅
        
        Args:
            product_id: 产品ID（订阅ID）
            purchase_token: 购买令牌
            
        Returns:
            验证结果字典
        """
        try:
            # 开发环境Mock响应
            if not self.service:
                if settings.ENVIRONMENT == "development":
                    logger.info(f"Mock Google verification for product: {product_id}")
                    return self._mock_verification_response(product_id)
                else:
                    return {
                        "is_valid": False,
                        "error": "Google Play service not initialized"
                    }
            
            logger.info(f"Verifying Google subscription: {product_id}")
            
            # 调用Google API验证订阅
            result = self.service.purchases().subscriptions().get(
                packageName=self.package_name,
                subscriptionId=product_id,
                token=purchase_token
            ).execute()
            
            # 处理验证结果
            processed = self._process_verification_result(result, product_id)
            
            # 如果订阅有效且未确认，自动确认
            if processed.get("is_valid") and processed.get("is_active"):
                if result.get("acknowledgementState", 0) == 0:
                    await self.acknowledge_subscription(product_id, purchase_token)
            
            return processed
            
        except HttpError as e:
            error_content = e.content.decode('utf-8') if e.content else str(e)
            logger.error(f"Google Play API error: {e.resp.status} - {error_content}")
            
            # 处理特定错误
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
            else:
                return {
                    "is_valid": False,
                    "error": f"API error: {e.resp.status}"
                }
        except Exception as e:
            logger.error(f"Google Play verification error: {str(e)}")
            return {
                "is_valid": False,
                "error": str(e)
            }
    
    def _process_verification_result(
        self, 
        result: Dict[str, Any],
        product_id: str
    ) -> Dict[str, Any]:
        """
        处理Google验证结果
        
        Args:
            result: Google API返回的结果
            product_id: 产品ID
            
        Returns:
            处理后的结果
        """
        # 检查支付状态
        # paymentState: 0 = Payment pending, 1 = Payment received, 2 = Free trial, 3 = Pending deferred upgrade/downgrade
        payment_state = result.get("paymentState", 0)
        
        # 检查确认状态
        # acknowledgementState: 0 = Yet to be acknowledged, 1 = Acknowledged
        acknowledgement_state = result.get("acknowledgementState", 0)
        
        # 检查取消原因
        # cancelReason: 0 = User canceled, 1 = System canceled (billing error), 2 = Replaced, 3 = Developer canceled
        cancel_reason = result.get("cancelReason")
        
        # 解析时间戳（毫秒）
        start_time_ms = result.get("startTimeMillis")
        expiry_time_ms = result.get("expiryTimeMillis")
        
        start_time = None
        expiry_time = None
        is_active = False
        
        if start_time_ms:
            start_time = datetime.fromtimestamp(int(start_time_ms) / 1000)
        
        if expiry_time_ms:
            expiry_time = datetime.fromtimestamp(int(expiry_time_ms) / 1000)
            # 订阅有效：未过期且支付已收到或试用中
            is_active = expiry_time > datetime.now() and payment_state in [1, 2]
        
        # 检查是否自动续订
        auto_renewing = result.get("autoRenewing", False)
        
        # 判断订阅类型
        subscription_type = self._get_subscription_type(product_id)
        
        # 获取价格信息
        price_amount = None
        currency = result.get("priceCurrencyCode", "USD")
        
        if result.get("priceAmountMicros"):
            # 价格以微单位存储（1美元 = 1,000,000微单位）
            price_amount = int(result.get("priceAmountMicros")) / 1000000
        elif subscription_type == "YEARLY":
            # 根据产品类型推断价格
            price_amount = settings.EARLY_BIRD_YEARLY_PRICE if "early" in product_id.lower() else settings.STANDARD_YEARLY_PRICE
        else:
            price_amount = settings.EARLY_BIRD_MONTHLY_PRICE if "early" in product_id.lower() else settings.STANDARD_MONTHLY_PRICE
        
        # 获取用户取消时间
        user_cancellation_time_ms = result.get("userCancellationTimeMillis")
        cancelled_at = None
        if user_cancellation_time_ms:
            cancelled_at = datetime.fromtimestamp(int(user_cancellation_time_ms) / 1000).isoformat()
        
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
            "is_in_grace_period": result.get("expiryTimeMillis") and payment_state == 0,  # 宽限期
            "cancel_reason": cancel_reason,
            "cancelled_at": cancelled_at,
            "price": price_amount,
            "currency": currency,
            "country_code": result.get("countryCode"),
            "developer_payload": result.get("developerPayload"),
            "linked_purchase_token": result.get("linkedPurchaseToken"),  # 用于升级/降级
            "raw_response": result
        }
    
    async def acknowledge_subscription(
        self,
        product_id: str,
        purchase_token: str
    ) -> bool:
        """
        确认订阅（Google要求在3天内确认）
        
        Args:
            product_id: 产品ID
            purchase_token: 购买令牌
            
        Returns:
            是否成功
        """
        try:
            if not self.service:
                return settings.ENVIRONMENT == "development"  # 开发环境返回True
            
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
                # 可能已经确认过了
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
        取消订阅
        
        Args:
            product_id: 产品ID
            purchase_token: 购买令牌
            
        Returns:
            是否成功
        """
        try:
            if not self.service:
                return settings.ENVIRONMENT == "development"
            
            logger.info(f"Cancelling Google subscription: {product_id}")
            
            self.service.purchases().subscriptions().cancel(
                packageName=self.package_name,
                subscriptionId=product_id,
                token=purchase_token
            ).execute()
            
            logger.info(f"Successfully cancelled subscription: {product_id}")
            return True
            
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
        延期订阅
        
        Args:
            product_id: 产品ID
            purchase_token: 购买令牌
            desired_expiry_time_ms: 期望的到期时间（毫秒）
            
        Returns:
            是否成功
        """
        try:
            if not self.service:
                return settings.ENVIRONMENT == "development"
            
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
            
        except Exception as e:
            logger.error(f"Failed to defer subscription: {str(e)}")
            return False
    
    def _get_subscription_type(self, product_id: str) -> str:
        """根据产品ID判断订阅类型"""
        if not product_id:
            return "MONTHLY"
        
        product_id_lower = product_id.lower()
        if "yearly" in product_id_lower or "annual" in product_id_lower:
            return "YEARLY"
        return "MONTHLY"
    
    def _mock_verification_response(self, product_id: str) -> Dict[str, Any]:
        """
        开发环境的Mock响应
        
        Args:
            product_id: 产品ID
            
        Returns:
            Mock验证结果
        """
        subscription_type = self._get_subscription_type(product_id)
        
        # 判断是否早鸟价格
        is_early_bird = "early" in product_id.lower()
        
        if subscription_type == "YEARLY":
            price = settings.EARLY_BIRD_YEARLY_PRICE if is_early_bird else settings.STANDARD_YEARLY_PRICE
            expiry_delta = timedelta(days=365)
        else:
            price = settings.EARLY_BIRD_MONTHLY_PRICE if is_early_bird else settings.STANDARD_MONTHLY_PRICE
            expiry_delta = timedelta(days=30)
        
        now = datetime.now()
        expiry_time = now + expiry_delta
        
        return {
            "is_valid": True,
            "is_active": True,
            "product_id": product_id,
            "order_id": f"GPA.mock-{now.timestamp()}",
            "purchase_token": f"mock-token-{now.timestamp()}",
            "subscription_type": subscription_type,
            "start_time": now.isoformat(),
            "expiry_time": expiry_time.isoformat(),
            "auto_renewing": True,
            "payment_state": 1,  # Payment received
            "acknowledgement_state": 1,  # Acknowledged
            "is_trial": False,
            "is_in_grace_period": False,
            "price": price,
            "currency": "USD",
            "country_code": "US",
            "is_mock": True
        }
    
    def process_rtdn_notification(self, notification_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理Google Real-time Developer Notification
        
        Args:
            notification_data: 通知数据
            
        Returns:
            处理结果
        """
        try:
            subscription_notification = notification_data.get("subscriptionNotification", {})
            
            notification_type = subscription_notification.get("notificationType")
            product_id = subscription_notification.get("subscriptionId")
            purchase_token = subscription_notification.get("purchaseToken")
            
            # 通知类型：
            # 1 = SUBSCRIPTION_RECOVERED - 从账号保留状态恢复
            # 2 = SUBSCRIPTION_RENEWED - 续订成功
            # 3 = SUBSCRIPTION_CANCELED - 用户取消
            # 4 = SUBSCRIPTION_PURCHASED - 新购买
            # 5 = SUBSCRIPTION_ON_HOLD - 账号保留
            # 6 = SUBSCRIPTION_IN_GRACE_PERIOD - 宽限期
            # 7 = SUBSCRIPTION_RESTARTED - 重新启动
            # 8 = SUBSCRIPTION_PRICE_CHANGE_CONFIRMED - 价格变更确认
            # 9 = SUBSCRIPTION_DEFERRED - 延期
            # 10 = SUBSCRIPTION_PAUSED - 暂停
            # 11 = SUBSCRIPTION_PAUSE_SCHEDULE_CHANGED - 暂停计划变更
            # 12 = SUBSCRIPTION_REVOKED - 撤销
            # 13 = SUBSCRIPTION_EXPIRED - 过期
            
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


# 创建服务实例
google_play_service = GooglePlayService()
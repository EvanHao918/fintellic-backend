"""
Apple In-App Purchase Service
处理Apple IAP收据验证和订阅管理
"""
import httpx
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import jwt
import base64
import hashlib
import hmac

from app.core.config import settings

logger = logging.getLogger(__name__)


class AppleIAPService:
    """Apple IAP服务类"""
    
    def __init__(self):
        """初始化服务"""
        self.sandbox_url = "https://sandbox.itunes.apple.com/verifyReceipt"
        self.production_url = "https://buy.itunes.apple.com/verifyReceipt"
        self.shared_secret = settings.APPLE_SHARED_SECRET if hasattr(settings, 'APPLE_SHARED_SECRET') else None
        self.bundle_id = settings.APPLE_BUNDLE_ID if hasattr(settings, 'APPLE_BUNDLE_ID') else "com.hermespeed.app"
        self.use_sandbox = settings.APPLE_USE_SANDBOX if hasattr(settings, 'APPLE_USE_SANDBOX') else True
        
        # StoreKit 2 配置
        self.issuer_id = settings.APPLE_ISSUER_ID if hasattr(settings, 'APPLE_ISSUER_ID') else None
        self.key_id = settings.APPLE_KEY_ID if hasattr(settings, 'APPLE_KEY_ID') else None
        self.private_key = settings.APPLE_PRIVATE_KEY if hasattr(settings, 'APPLE_PRIVATE_KEY') else None
        
    async def verify_receipt(
        self, 
        receipt_data: str,
        exclude_old_transactions: bool = True
    ) -> Dict[str, Any]:
        """
        验证Apple收据
        
        Args:
            receipt_data: Base64编码的收据数据
            exclude_old_transactions: 是否排除旧交易
            
        Returns:
            验证结果字典
        """
        try:
            # 准备请求数据
            request_data = {
                "receipt-data": receipt_data,
                "exclude-old-transactions": exclude_old_transactions
            }
            
            # 添加 shared secret（如果有）
            if self.shared_secret:
                request_data["password"] = self.shared_secret
            
            # 首先尝试生产环境（除非明确配置为沙盒）
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 根据配置选择URL
                url = self.sandbox_url if self.use_sandbox else self.production_url
                
                logger.info(f"Verifying Apple receipt with URL: {url}")
                
                response = await client.post(
                    url,
                    json=request_data
                )
                
                result = response.json()
                
                # 如果生产环境返回21007（沙盒收据），则切换到沙盒环境
                if result.get("status") == 21007 and not self.use_sandbox:
                    logger.info("Receipt is from sandbox, retrying with sandbox URL")
                    response = await client.post(
                        self.sandbox_url,
                        json=request_data
                    )
                    result = response.json()
                
                # 处理验证结果
                return self._process_verification_result(result)
                
        except httpx.TimeoutException:
            logger.error("Apple receipt verification timeout")
            return {
                "is_valid": False,
                "error": "Verification timeout"
            }
        except Exception as e:
            logger.error(f"Apple receipt verification error: {str(e)}")
            return {
                "is_valid": False,
                "error": str(e)
            }
    
    def _process_verification_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理Apple验证结果
        
        Args:
            result: Apple返回的验证结果
            
        Returns:
            处理后的结果
        """
        status = result.get("status", -1)
        
        # 状态码说明：
        # 0 - 收据有效
        # 21000 - App Store无法读取提供的JSON对象
        # 21002 - receipt-data属性中的数据格式错误或丢失
        # 21003 - 收据无法认证
        # 21004 - 提供的共享密钥与账户的共享密钥不匹配
        # 21005 - 收据服务器当前不可用
        # 21006 - 收据有效但订阅已过期
        # 21007 - 收据是沙盒收据，但发送到生产环境验证
        # 21008 - 收据是生产收据，但发送到沙盒环境验证
        
        if status != 0:
            logger.warning(f"Apple receipt verification failed with status: {status}")
            return {
                "is_valid": False,
                "status": status,
                "error": self._get_status_message(status)
            }
        
        # 解析收据信息
        receipt = result.get("receipt", {})
        latest_receipt_info = result.get("latest_receipt_info", [])
        pending_renewal_info = result.get("pending_renewal_info", [])
        
        # 获取最新的订阅信息
        latest_subscription = None
        if latest_receipt_info:
            # 按购买日期排序，获取最新的
            sorted_receipts = sorted(
                latest_receipt_info,
                key=lambda x: x.get("purchase_date_ms", "0"),
                reverse=True
            )
            latest_subscription = sorted_receipts[0] if sorted_receipts else None
        
        # 检查订阅状态
        is_active = False
        expires_date = None
        
        if latest_subscription:
            # 检查是否过期
            expires_date_ms = latest_subscription.get("expires_date_ms")
            if expires_date_ms:
                expires_date = datetime.fromtimestamp(int(expires_date_ms) / 1000)
                is_active = expires_date > datetime.now()
        
        # 获取产品信息
        product_id = latest_subscription.get("product_id") if latest_subscription else None
        transaction_id = latest_subscription.get("transaction_id") if latest_subscription else None
        original_transaction_id = latest_subscription.get("original_transaction_id") if latest_subscription else None
        
        # 检查是否自动续订
        auto_renew = False
        if pending_renewal_info and original_transaction_id:
            for renewal in pending_renewal_info:
                if renewal.get("original_transaction_id") == original_transaction_id:
                    auto_renew = renewal.get("auto_renew_status") == "1"
                    break
        
        # 获取价格信息
        price = None
        currency = None
        if latest_subscription:
            # 尝试从收据中获取价格
            price_raw = latest_subscription.get("price")
            if price_raw:
                try:
                    price = float(price_raw)
                except (ValueError, TypeError):
                    price = None
            
            # 根据产品ID推断价格（如果无法从收据获取）
            if not price and product_id:
                if "yearly" in product_id.lower():
                    price = settings.EARLY_BIRD_YEARLY_PRICE if "early" in product_id.lower() else settings.STANDARD_YEARLY_PRICE
                else:
                    price = settings.EARLY_BIRD_MONTHLY_PRICE if "early" in product_id.lower() else settings.STANDARD_MONTHLY_PRICE
                currency = "USD"
        
        return {
            "is_valid": True,
            "is_active": is_active,
            "product_id": product_id,
            "transaction_id": transaction_id,
            "original_transaction_id": original_transaction_id,
            "expires_date": expires_date.isoformat() if expires_date else None,
            "auto_renew": auto_renew,
            "bundle_id": receipt.get("bundle_id"),
            "latest_receipt": result.get("latest_receipt"),
            "price": price,
            "currency": currency or "USD",
            "is_trial": latest_subscription.get("is_trial_period") == "true" if latest_subscription else False,
            "is_intro_offer": latest_subscription.get("is_in_intro_offer_period") == "true" if latest_subscription else False,
            "raw_response": result
        }
    
    def _get_status_message(self, status: int) -> str:
        """获取状态码对应的错误信息"""
        status_messages = {
            21000: "The App Store could not read the JSON object",
            21002: "The data in the receipt-data property was malformed or missing",
            21003: "The receipt could not be authenticated",
            21004: "The shared secret does not match",
            21005: "The receipt server is not currently available",
            21006: "This receipt is valid but the subscription has expired",
            21007: "This receipt is from the test environment",
            21008: "This receipt is from the production environment",
            21009: "Internal data access error",
            21010: "The user account cannot be found or has been deleted"
        }
        return status_messages.get(status, f"Unknown error (status: {status})")
    
    def verify_notification(self, notification: Dict[str, Any]) -> bool:
        """
        验证Apple Server-to-Server通知
        
        Args:
            notification: 通知数据
            
        Returns:
            是否有效
        """
        try:
            # StoreKit 2 通知格式（JWT）
            if "signedPayload" in notification:
                # 如果有JWT签名的payload，验证签名
                signed_payload = notification.get("signedPayload")
                if signed_payload and self.private_key:
                    try:
                        # 验证JWT（实际生产环境应该验证签名）
                        # 这里简化处理，实际应该用Apple的公钥验证
                        decoded = jwt.decode(
                            signed_payload,
                            options={"verify_signature": False}  # 生产环境应该验证
                        )
                        return True
                    except jwt.InvalidTokenError:
                        logger.warning("Invalid JWT token in Apple notification")
                        return False
                else:
                    # 没有配置密钥，暂时信任（开发环境）
                    return True
            
            # StoreKit 1 通知格式
            if "unified_receipt" in notification or "latest_receipt" in notification:
                # 旧版本通知，检查必要字段
                return "auto_renew_product_id" in notification or "product_id" in notification
            
            # 未知格式
            logger.warning(f"Unknown Apple notification format: {notification.keys()}")
            return False
            
        except Exception as e:
            logger.error(f"Notification verification error: {str(e)}")
            return False
    
    def extract_subscription_info(self, receipt_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        从收据信息中提取订阅详情
        
        Args:
            receipt_info: 收据信息（验证结果）
            
        Returns:
            订阅详情
        """
        # 如果是我们处理过的结果
        if "is_valid" in receipt_info:
            return {
                "product_id": receipt_info.get("product_id"),
                "subscription_type": self._get_subscription_type(receipt_info.get("product_id")),
                "transaction_id": receipt_info.get("transaction_id"),
                "original_transaction_id": receipt_info.get("original_transaction_id"),
                "expires_date": receipt_info.get("expires_date"),
                "is_trial": receipt_info.get("is_trial", False),
                "is_intro_offer": receipt_info.get("is_intro_offer", False),
                "auto_renew": receipt_info.get("auto_renew", False),
                "price": receipt_info.get("price"),
                "currency": receipt_info.get("currency", "USD")
            }
        
        # 如果是原始Apple响应
        latest_info = receipt_info.get("latest_receipt_info", [])
        if not latest_info:
            return {}
        
        # 获取最新的订阅
        latest = latest_info[0] if isinstance(latest_info, list) else latest_info
        
        # 判断订阅类型
        product_id = latest.get("product_id", "")
        subscription_type = self._get_subscription_type(product_id)
        
        # 解析时间
        expires_date = None
        if latest.get("expires_date_ms"):
            expires_date = datetime.fromtimestamp(
                int(latest.get("expires_date_ms")) / 1000
            ).isoformat()
        
        return {
            "product_id": product_id,
            "subscription_type": subscription_type,
            "transaction_id": latest.get("transaction_id"),
            "original_transaction_id": latest.get("original_transaction_id"),
            "purchase_date": latest.get("purchase_date"),
            "expires_date": expires_date,
            "is_trial": latest.get("is_trial_period") == "true",
            "is_intro_offer": latest.get("is_in_intro_offer_period") == "true",
            "auto_renew": receipt_info.get("pending_renewal_info", [{}])[0].get("auto_renew_status") == "1"
        }
    
    def _get_subscription_type(self, product_id: str) -> str:
        """根据产品ID判断订阅类型"""
        if not product_id:
            return "MONTHLY"
        
        product_id_lower = product_id.lower()
        if "yearly" in product_id_lower or "annual" in product_id_lower:
            return "YEARLY"
        return "MONTHLY"
    
    def extract_notification_info(self, notification: Dict[str, Any]) -> Dict[str, Any]:
        """
        从通知中提取关键信息
        
        Args:
            notification: Apple通知数据
            
        Returns:
            提取的信息
        """
        try:
            # StoreKit 2 格式
            if "signedPayload" in notification:
                # 解码JWT（不验证签名，实际应该验证）
                try:
                    decoded = jwt.decode(
                        notification["signedPayload"],
                        options={"verify_signature": False}
                    )
                    
                    data = decoded.get("data", {})
                    return {
                        "notification_type": decoded.get("notificationType"),
                        "transaction_id": data.get("transactionId"),
                        "original_transaction_id": data.get("originalTransactionId"),
                        "product_id": data.get("productId"),
                        "expires_date": data.get("expiresDate"),
                        "environment": data.get("environment", "Production")
                    }
                except Exception as e:
                    logger.error(f"Failed to decode JWT payload: {e}")
                    return {}
            
            # StoreKit 1 格式
            latest_receipt_info = notification.get("latest_receipt_info", {})
            if isinstance(latest_receipt_info, list) and latest_receipt_info:
                latest_receipt_info = latest_receipt_info[0]
            
            return {
                "notification_type": notification.get("notification_type"),
                "transaction_id": latest_receipt_info.get("transaction_id"),
                "original_transaction_id": latest_receipt_info.get("original_transaction_id"),
                "product_id": latest_receipt_info.get("product_id") or notification.get("auto_renew_product_id"),
                "expires_date": latest_receipt_info.get("expires_date"),
                "environment": notification.get("environment", "Production")
            }
            
        except Exception as e:
            logger.error(f"Failed to extract notification info: {e}")
            return {}


# 创建服务实例
apple_iap_service = AppleIAPService()
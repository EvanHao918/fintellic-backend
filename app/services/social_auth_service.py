"""
Social Authentication Service
=============================
处理 Apple Sign In 和 Google Sign In 的 token 验证

Apple Sign In 流程:
1. 前端使用 expo-apple-authentication 获取 identityToken
2. 后端验证 identityToken (JWT) 的签名和声明
3. 提取 apple_user_id (sub) 和 email

Google Sign In 流程:
1. 前端使用 expo-auth-session 或 @react-native-google-signin 获取 idToken
2. 后端验证 idToken 的签名和声明
3. 提取 google_user_id (sub) 和 email
"""

import logging
from typing import Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# ==================== 数据类 ====================

@dataclass
class SocialUserInfo:
    """社交登录返回的用户信息"""
    provider: str           # "apple" 或 "google"
    user_id: str           # Apple/Google 的唯一用户ID
    email: Optional[str]    # 邮箱（Apple 可能隐藏）
    email_verified: bool    # 邮箱是否已验证
    full_name: Optional[str] = None  # 用户全名
    given_name: Optional[str] = None  # 名
    family_name: Optional[str] = None  # 姓


# ==================== Apple Sign In ====================

class AppleAuthService:
    """
    Apple Sign In 验证服务
    
    Apple 的 identityToken 是一个 JWT，包含：
    - iss: https://appleid.apple.com
    - aud: 你的 Bundle ID (com.hermespeed.app)
    - sub: Apple 用户唯一ID（每个 app 不同）
    - email: 用户邮箱（首次登录时提供，可能隐藏）
    - email_verified: 邮箱是否验证
    """
    
    APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
    APPLE_ISSUER = "https://appleid.apple.com"
    
    _cached_keys = None
    _keys_fetched_at = None
    _keys_cache_duration = 3600  # 缓存1小时
    
    @classmethod
    async def get_apple_public_keys(cls) -> dict:
        """获取 Apple 的公钥（用于验证 JWT 签名）"""
        now = datetime.now(timezone.utc).timestamp()
        
        # 检查缓存
        if cls._cached_keys and cls._keys_fetched_at:
            if now - cls._keys_fetched_at < cls._keys_cache_duration:
                return cls._cached_keys
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(cls.APPLE_KEYS_URL, timeout=10.0)
                response.raise_for_status()
                cls._cached_keys = response.json()
                cls._keys_fetched_at = now
                logger.info("✅ Apple public keys fetched successfully")
                return cls._cached_keys
        except Exception as e:
            logger.error(f"❌ Failed to fetch Apple public keys: {e}")
            # 如果有缓存，返回缓存（即使过期）
            if cls._cached_keys:
                logger.warning("Using cached Apple keys")
                return cls._cached_keys
            raise
    
    @classmethod
    def _get_key_from_jwks(cls, keys: dict, kid: str) -> Optional[dict]:
        """从 JWKS 中找到匹配的公钥"""
        for key in keys.get("keys", []):
            if key.get("kid") == kid:
                return key
        return None
    
    @classmethod
    async def verify_identity_token(
        cls,
        identity_token: str,
        full_name: Optional[str] = None
    ) -> Tuple[bool, Optional[SocialUserInfo], Optional[str]]:
        """
        验证 Apple identityToken
        
        Args:
            identity_token: 前端获取的 JWT token
            full_name: 用户全名（仅首次登录时前端提供）
        
        Returns:
            (success, user_info, error_message)
        """
        try:
            # 1. 解码 token header 获取 kid
            unverified_header = jwt.get_unverified_header(identity_token)
            kid = unverified_header.get("kid")
            
            if not kid:
                return False, None, "Token header missing 'kid'"
            
            # 2. 获取 Apple 公钥
            keys = await cls.get_apple_public_keys()
            key_data = cls._get_key_from_jwks(keys, kid)
            
            if not key_data:
                return False, None, f"No matching key found for kid: {kid}"
            
            # 3. 构建公钥
            from jwt.algorithms import RSAAlgorithm
            public_key = RSAAlgorithm.from_jwk(key_data)
            
            # 4. 验证并解码 token
            # 允许的 audience 包括 Bundle ID
            valid_audiences = [settings.APPLE_BUNDLE_ID]
            if settings.APPLE_SERVICE_ID:
                valid_audiences.append(settings.APPLE_SERVICE_ID)
            
            decoded = jwt.decode(
                identity_token,
                public_key,
                algorithms=["RS256"],
                audience=valid_audiences,
                issuer=cls.APPLE_ISSUER,
            )
            
            # 5. 提取用户信息
            apple_user_id = decoded.get("sub")
            email = decoded.get("email")
            email_verified = decoded.get("email_verified", False)
            
            # Apple 的 email_verified 可能是字符串 "true"
            if isinstance(email_verified, str):
                email_verified = email_verified.lower() == "true"
            
            if not apple_user_id:
                return False, None, "Token missing 'sub' claim"
            
            user_info = SocialUserInfo(
                provider="apple",
                user_id=apple_user_id,
                email=email,
                email_verified=email_verified,
                full_name=full_name,  # 前端传入
            )
            
            logger.info(f"✅ Apple token verified for user: {apple_user_id[:8]}...")
            return True, user_info, None
            
        except jwt.ExpiredSignatureError:
            return False, None, "Token has expired"
        except jwt.InvalidAudienceError:
            return False, None, "Invalid audience"
        except jwt.InvalidIssuerError:
            return False, None, "Invalid issuer"
        except jwt.InvalidTokenError as e:
            return False, None, f"Invalid token: {str(e)}"
        except Exception as e:
            logger.error(f"❌ Apple token verification error: {e}")
            return False, None, f"Verification failed: {str(e)}"


# ==================== Google Sign In ====================

class GoogleAuthService:
    """
    Google Sign In 验证服务
    
    Google 的 idToken 是一个 JWT，包含：
    - iss: https://accounts.google.com
    - aud: 你的 Google Client ID
    - sub: Google 用户唯一ID
    - email: 用户邮箱
    - email_verified: 邮箱是否验证
    - name: 用户全名
    - given_name: 名
    - family_name: 姓
    """
    
    GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
    GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"
    GOOGLE_ISSUERS = ["https://accounts.google.com", "accounts.google.com"]
    
    _cached_keys = None
    _keys_fetched_at = None
    _keys_cache_duration = 3600
    
    @classmethod
    async def get_google_public_keys(cls) -> dict:
        """获取 Google 的公钥"""
        now = datetime.now(timezone.utc).timestamp()
        
        if cls._cached_keys and cls._keys_fetched_at:
            if now - cls._keys_fetched_at < cls._keys_cache_duration:
                return cls._cached_keys
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(cls.GOOGLE_CERTS_URL, timeout=10.0)
                response.raise_for_status()
                cls._cached_keys = response.json()
                cls._keys_fetched_at = now
                logger.info("✅ Google public keys fetched successfully")
                return cls._cached_keys
        except Exception as e:
            logger.error(f"❌ Failed to fetch Google public keys: {e}")
            if cls._cached_keys:
                logger.warning("Using cached Google keys")
                return cls._cached_keys
            raise
    
    @classmethod
    def _get_key_from_jwks(cls, keys: dict, kid: str) -> Optional[dict]:
        """从 JWKS 中找到匹配的公钥"""
        for key in keys.get("keys", []):
            if key.get("kid") == kid:
                return key
        return None
    
    @classmethod
    async def verify_id_token(cls, id_token: str) -> Tuple[bool, Optional[SocialUserInfo], Optional[str]]:
        """
        验证 Google idToken
        
        Args:
            id_token: 前端获取的 JWT token
        
        Returns:
            (success, user_info, error_message)
        """
        try:
            # 1. 解码 token header
            unverified_header = jwt.get_unverified_header(id_token)
            kid = unverified_header.get("kid")
            
            if not kid:
                return False, None, "Token header missing 'kid'"
            
            # 2. 获取 Google 公钥
            keys = await cls.get_google_public_keys()
            key_data = cls._get_key_from_jwks(keys, kid)
            
            if not key_data:
                return False, None, f"No matching key found for kid: {kid}"
            
            # 3. 构建公钥
            from jwt.algorithms import RSAAlgorithm
            public_key = RSAAlgorithm.from_jwk(key_data)
            
            # 4. 验证并解码 token
            # 允许的 audience: iOS Client ID 和 Web Client ID
            valid_audiences = []
            if settings.GOOGLE_CLIENT_ID_IOS:
                valid_audiences.append(settings.GOOGLE_CLIENT_ID_IOS)
            if settings.GOOGLE_CLIENT_ID_WEB:
                valid_audiences.append(settings.GOOGLE_CLIENT_ID_WEB)
            if settings.GOOGLE_CLIENT_ID_ANDROID:
                valid_audiences.append(settings.GOOGLE_CLIENT_ID_ANDROID)
            
            if not valid_audiences:
                return False, None, "No Google Client IDs configured"
            
            decoded = jwt.decode(
                id_token,
                public_key,
                algorithms=["RS256"],
                audience=valid_audiences,
                issuer=cls.GOOGLE_ISSUERS,
            )
            
            # 5. 提取用户信息
            google_user_id = decoded.get("sub")
            email = decoded.get("email")
            email_verified = decoded.get("email_verified", False)
            
            if not google_user_id:
                return False, None, "Token missing 'sub' claim"
            
            user_info = SocialUserInfo(
                provider="google",
                user_id=google_user_id,
                email=email,
                email_verified=email_verified,
                full_name=decoded.get("name"),
                given_name=decoded.get("given_name"),
                family_name=decoded.get("family_name"),
            )
            
            logger.info(f"✅ Google token verified for user: {google_user_id[:8]}...")
            return True, user_info, None
            
        except jwt.ExpiredSignatureError:
            return False, None, "Token has expired"
        except jwt.InvalidAudienceError:
            return False, None, "Invalid audience"
        except jwt.InvalidIssuerError:
            return False, None, "Invalid issuer"
        except jwt.InvalidTokenError as e:
            return False, None, f"Invalid token: {str(e)}"
        except Exception as e:
            logger.error(f"❌ Google token verification error: {e}")
            return False, None, f"Verification failed: {str(e)}"
    
    @classmethod
    async def verify_id_token_simple(cls, id_token: str) -> Tuple[bool, Optional[SocialUserInfo], Optional[str]]:
        """
        使用 Google tokeninfo API 验证 token（简化方法，作为备选）
        
        这个方法不需要处理公钥，但依赖 Google API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    cls.GOOGLE_TOKEN_INFO_URL,
                    params={"id_token": id_token},
                    timeout=10.0
                )
                
                if response.status_code != 200:
                    return False, None, f"Token validation failed: {response.text}"
                
                data = response.json()
                
                # 验证 audience
                aud = data.get("aud")
                valid_audiences = [
                    settings.GOOGLE_CLIENT_ID_IOS,
                    settings.GOOGLE_CLIENT_ID_WEB,
                    settings.GOOGLE_CLIENT_ID_ANDROID,
                ]
                
                if aud not in [a for a in valid_audiences if a]:
                    return False, None, f"Invalid audience: {aud}"
                
                user_info = SocialUserInfo(
                    provider="google",
                    user_id=data.get("sub"),
                    email=data.get("email"),
                    email_verified=data.get("email_verified") == "true",
                    full_name=data.get("name"),
                    given_name=data.get("given_name"),
                    family_name=data.get("family_name"),
                )
                
                return True, user_info, None
                
        except Exception as e:
            logger.error(f"❌ Google token verification (simple) error: {e}")
            return False, None, f"Verification failed: {str(e)}"


# ==================== 统一入口 ====================

class SocialAuthService:
    """社交登录统一服务入口"""
    
    @staticmethod
    async def verify_apple_token(
        identity_token: str,
        full_name: Optional[str] = None
    ) -> Tuple[bool, Optional[SocialUserInfo], Optional[str]]:
        """验证 Apple Sign In token"""
        return await AppleAuthService.verify_identity_token(identity_token, full_name)
    
    @staticmethod
    async def verify_google_token(
        id_token: str
    ) -> Tuple[bool, Optional[SocialUserInfo], Optional[str]]:
        """验证 Google Sign In token"""
        return await GoogleAuthService.verify_id_token(id_token)


# 创建全局实例
social_auth_service = SocialAuthService()
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, validator


# Token schemas
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_info: Optional[Dict[str, Any]] = None


class TokenData(BaseModel):
    username: Optional[str] = None


# Login schemas
class LoginRequest(BaseModel):
    """Login request schema"""
    email: EmailStr
    password: str
    device_id: Optional[str] = None
    device_type: Optional[str] = None  # ios, android, web


# Registration schemas
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = None
    username: Optional[str] = None
    promo_code: Optional[str] = None
    referral_code: Optional[str] = None
    device_id: Optional[str] = None
    device_type: Optional[str] = None  # ios, android, web
    registration_source: Optional[str] = None  # email, apple, google, linkedin
    
    @validator('password')
    def validate_password_strength(cls, v):
        """确保密码符合安全要求"""
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(char.islower() for char in v):
            raise ValueError('Password must contain at least one lowercase letter')
        return v


class RegisterResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    username: Optional[str] = None
    access_token: str
    refresh_token: str
    
    # 订阅相关信息
    tier: str
    is_early_bird: bool
    pricing_tier: Optional[str] = None
    user_sequence_number: Optional[int] = None
    monthly_price: float
    yearly_price: float
    early_bird_slots_remaining: Optional[int] = None
    
    class Config:
        from_attributes = True


# ==================== PASSWORD RESET SCHEMAS ====================
class PasswordResetRequest(BaseModel):
    """请求密码重置"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """确认密码重置"""
    token: str = Field(..., min_length=1, max_length=255)
    new_password: str = Field(..., min_length=8, max_length=100)
    
    @validator('new_password')
    def validate_password_strength(cls, v):
        """确保新密码符合安全要求"""
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(char.islower() for char in v):
            raise ValueError('Password must contain at least one lowercase letter')
        return v


class PasswordResetResponse(BaseModel):
    """密码重置响应"""
    message: str
    success: bool = False
    can_retry_after: Optional[datetime] = None
# ================================================================


# Refresh token
class RefreshTokenRequest(BaseModel):
    refresh_token: str


# Device management
class DeviceInfo(BaseModel):
    device_id: str
    device_type: str  # ios, android, web
    device_model: Optional[str] = None
    device_name: Optional[str] = None
    app_version: Optional[str] = None
    os_version: Optional[str] = None
    push_token: Optional[str] = None
    biometric_enabled: bool = False


class DeviceRegisterRequest(BaseModel):
    device_info: DeviceInfo
    enable_biometric: bool = False


class DeviceListResponse(BaseModel):
    devices: list[DeviceInfo]
    current_device_id: Optional[str] = None


# ==================== ENHANCED ERROR RESPONSES ====================
class AuthErrorResponse(BaseModel):
    """标准化的认证错误响应"""
    error: str
    message: str
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ValidationErrorDetail(BaseModel):
    """验证错误详情"""
    field: str
    message: str
    error_type: str


class ValidationErrorResponse(BaseModel):
    """验证错误响应"""
    error: str = "validation_error"
    message: str = "Validation failed"
    details: list[ValidationErrorDetail]
# ================================================================


# ==================== ACCOUNT SECURITY SCHEMAS ====================
class SecurityInfoResponse(BaseModel):
    """账户安全信息响应"""
    email_verified: bool
    has_password: bool
    social_providers: list[str]  # ["apple", "google", "linkedin"]
    biometric_enabled: bool
    two_factor_enabled: bool = False
    last_login_at: Optional[datetime] = None
    login_attempts_today: int = 0
    is_account_locked: bool = False


class ChangePasswordRequest(BaseModel):
    """修改密码请求（已登录用户）"""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
    
    @validator('new_password')
    def validate_new_password(cls, v, values):
        """验证新密码"""
        if 'current_password' in values and v == values['current_password']:
            raise ValueError('New password must be different from current password')
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(char.islower() for char in v):
            raise ValueError('Password must contain at least one lowercase letter')
        return v
# ================================================================
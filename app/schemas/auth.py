from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# Token schemas
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_info: Optional[Dict[str, Any]] = None  # 添加用户信息


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
    promo_code: Optional[str] = None  # 优惠码
    referral_code: Optional[str] = None  # 推荐码
    device_id: Optional[str] = None
    device_type: Optional[str] = None  # ios, android, web
    registration_source: Optional[str] = None  # email, apple, google, linkedin


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


# Social authentication schemas
class AppleSignInRequest(BaseModel):
    identity_token: str
    authorization_code: str
    user_id: str  # Apple user identifier
    email: Optional[str] = None
    full_name: Optional[str] = None
    device_id: Optional[str] = None


class GoogleSignInRequest(BaseModel):
    id_token: str
    user_id: str  # Google user ID
    email: str
    full_name: Optional[str] = None
    photo_url: Optional[str] = None
    device_id: Optional[str] = None


class LinkedInSignInRequest(BaseModel):
    access_token: str
    user_id: str
    email: str
    full_name: Optional[str] = None
    profile_url: Optional[str] = None
    device_id: Optional[str] = None


# Biometric authentication
class BiometricAuthRequest(BaseModel):
    refresh_token: str
    biometric_type: str  # face_id, touch_id, fingerprint
    device_id: str
    device_model: Optional[str] = None


# Refresh token
class RefreshTokenRequest(BaseModel):
    refresh_token: str


# Password reset schemas
class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)


# Email verification
class EmailVerificationRequest(BaseModel):
    token: str


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
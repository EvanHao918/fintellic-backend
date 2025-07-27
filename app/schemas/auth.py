from typing import Optional
from pydantic import BaseModel, EmailStr


class Token(BaseModel):
    """Token response schema"""
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None


class TokenData(BaseModel):
    """Token payload data"""
    user_id: Optional[int] = None


class LoginRequest(BaseModel):
    """Login request schema"""
    email: EmailStr
    password: str
    device_id: Optional[str] = None


class RegisterRequest(BaseModel):
    """Registration request schema"""
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    username: Optional[str] = None
    device_id: Optional[str] = None
    device_type: Optional[str] = None
    registration_source: Optional[str] = None


class RegisterResponse(BaseModel):
    """Registration response schema"""
    id: int
    email: str
    full_name: Optional[str] = None
    username: Optional[str] = None
    message: str = "User registered successfully"
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    
    class Config:
        orm_mode = True
        from_attributes = True


# Social Authentication
class AppleSignInRequest(BaseModel):
    """Apple Sign In request"""
    identity_token: str
    authorization_code: str
    user_id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    device_id: Optional[str] = None


class GoogleSignInRequest(BaseModel):
    """Google Sign In request"""
    id_token: str
    user_id: str
    email: str
    full_name: Optional[str] = None
    photo_url: Optional[str] = None
    device_id: Optional[str] = None


# Biometric Authentication
class BiometricAuthRequest(BaseModel):
    """Biometric authentication request"""
    refresh_token: str
    device_id: str
    biometric_type: str  # face_id, touch_id, fingerprint


# Token Refresh
class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str


# Password Reset (existing)
class PasswordResetRequest(BaseModel):
    """Password reset request schema"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation schema"""
    token: str
    new_password: str
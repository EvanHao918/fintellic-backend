from pydantic_settings import BaseSettings
from typing import Optional, List
import os

class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    
    # API
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "AllSight"
    
    # Database
    DATABASE_URL: str
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days (Ã¤Â¿Â®Ã¦"Â¹: Ã¤Â»Å½7Ã¥Â¤Â©Ã¦"Â¹Ã¤Â¸Âº30Ã¥Â¤Â©)
    
    # OpenAI
    OPENAI_API_KEY: str
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Celery configuration
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    # SEC EDGAR
    SEC_USER_AGENT: str
    SEC_BASE_URL: str = "https://www.sec.gov"
    SEC_ARCHIVE_URL: str = "https://www.sec.gov/Archives/edgar/data"
    
    # Limits
    FREE_USER_DAILY_LIMIT: int = 3
    
    # ==================== SIMPLIFIED SUBSCRIPTION SETTINGS ====================
    # Simple monthly-only subscription with two price tiers
    
    # Price control switch - toggle between discounted and standard pricing
    USE_DISCOUNTED_PRICING: bool = True  # True=show $19.99, False=show $29.99
    
    # Monthly prices (only monthly subscription, no yearly)
    DISCOUNTED_MONTHLY_PRICE: float = 19.99  # Limited-time promotional price
    STANDARD_MONTHLY_PRICE: float = 29.99    # Standard price
    
    # Note: No yearly subscription - simplified single-tier monthly model
    
    # ==================== APPLE IN-APP PURCHASE ====================
    # Apple IAP Production Configuration
    APPLE_SHARED_SECRET: Optional[str] = None
    APPLE_BUNDLE_ID: str = "com.allsight.app"
    APPLE_USE_SANDBOX: bool = True  # Auto-detect based on environment
    
    # Apple IAP URLs
    APPLE_VERIFY_RECEIPT_URL: str = "https://buy.itunes.apple.com/verifyReceipt"
    APPLE_SANDBOX_VERIFY_URL: str = "https://sandbox.itunes.apple.com/verifyReceipt"
    
    # Apple Product IDs - Two separate products for manual price switching
    APPLE_MONTHLY_PRODUCT_ID_DISCOUNTED: str = "com.allsight.pro.monthly.discounted"  # $19.99
    APPLE_MONTHLY_PRODUCT_ID_STANDARD: str = "com.allsight.pro.monthly.standard"      # $29.99
    
    # Active product ID (controlled by USE_DISCOUNTED_PRICING flag)
    @property
    def APPLE_MONTHLY_PRODUCT_ID(self) -> str:
        """Get active Apple product ID based on pricing mode"""
        return self.APPLE_MONTHLY_PRODUCT_ID_DISCOUNTED if self.USE_DISCOUNTED_PRICING else self.APPLE_MONTHLY_PRODUCT_ID_STANDARD
    
    # Apple StoreKit 2 Configuration (optional for advanced features)
    APPLE_ISSUER_ID: Optional[str] = None
    APPLE_KEY_ID: Optional[str] = None
    APPLE_PRIVATE_KEY: Optional[str] = None
    
    # ==================== GOOGLE PLAY BILLING ====================
    # Google Play - DISABLED (iOS only for now)
    # Kept for future expansion but not actively used
    GOOGLE_PACKAGE_NAME: str = "com.allsight.app"
    GOOGLE_SERVICE_ACCOUNT_KEY_PATH: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_KEY_BASE64: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_KEY_JSON: Optional[str] = None
    GOOGLE_MONTHLY_PRODUCT_ID: str = "allsight_pro_monthly"  # Not in use
    
    # ==================== WEBHOOK CONFIGURATION ====================
    # Production Webhook URLs
    WEBHOOK_BASE_URL: Optional[str] = None  # https://api.hermespeed.com
    APPLE_WEBHOOK_PATH: str = "/api/v1/subscriptions/webhook/apple"
    GOOGLE_WEBHOOK_PATH: str = "/api/v1/subscriptions/webhook/google"
    
    # ==================== PAYMENT FEATURES ====================
    # Payment Features Control
    ENABLE_SUBSCRIPTION: bool = True
    ENABLE_TRIAL_PERIOD: bool = False
    TRIAL_PERIOD_DAYS: int = 7
    GRACE_PERIOD_DAYS: int = 3
    
    # Mock Payment Settings - PRODUCTION SAFE
    @property
    def ENABLE_MOCK_PAYMENTS(self) -> bool:
        """Enable mock payments ONLY in development environment"""
        return self.ENVIRONMENT == "development"
    
    # ==================== EMAIL CONFIGURATION ====================
    # Email service configuration
    ENABLE_PASSWORD_RESET: bool = True
    
    # SMTP Configuration
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    
    # Email settings
    EMAIL_FROM_NAME: str = "HermeSpeed"
    EMAIL_FROM_ADDRESS: Optional[str] = None
    PASSWORD_RESET_EXPIRE_HOURS: int = 1
    
    # Frontend URL for email links
    FRONTEND_URL: str = "http://localhost:19006"
    
    # ==================== NOTIFICATION CONFIGURATION ====================
    # Push Notifications
    FIREBASE_ENABLED: bool = True
    FIREBASE_SERVICE_ACCOUNT_KEY: Optional[str] = None
    FIREBASE_SERVICE_ACCOUNT_PATH: Optional[str] = None
    
    # FCM Settings
    FCM_SERVER_KEY: Optional[str] = None
    FCM_SENDER_ID: Optional[str] = None
    
    # Notification Settings
    NOTIFICATION_BATCH_SIZE: int = 500
    NOTIFICATION_RATE_LIMIT: int = 100
    NOTIFICATION_RETRY_ATTEMPTS: int = 3
    NOTIFICATION_RETRY_DELAY: int = 5
    
    # Notification Features
    ENABLE_FILING_NOTIFICATIONS: bool = True
    ENABLE_DAILY_RESET_NOTIFICATIONS: bool = True
    ENABLE_SUBSCRIPTION_NOTIFICATIONS: bool = True
    
    # Daily Reset Time (EST)
    DAILY_RESET_HOUR: int = 0
    DAILY_RESET_MINUTE: int = 0
    
    # ==================== PROCESSING SETTINGS ====================
    # Scheduler settings
    SCHEDULER_INTERVAL_MINUTES: int = 1
    FILING_LOOKBACK_MINUTES: int = 2
    
    # Processing settings
    MAX_CONCURRENT_DOWNLOADS: int = 3
    MAX_CONCURRENT_AI_TASKS: int = 2
    
    # ✅ UPDATED: AI Model Configuration - Switched to o3-mini for enhanced reasoning
    AI_MODEL: str = "o3-mini"  # Changed from gpt-4o-search-preview to o3-mini
    AI_MAX_TOKENS: int = 16000
    WEB_SEARCH_ENABLED: bool = True  # o3-mini supports autonomous web search and tool use
    
    # AI Generation Parameters
    AI_TEMPERATURE: float = 0.3
    AI_UNIFIED_ANALYSIS_MAX_TOKENS: int = 2000
    AI_FEED_SUMMARY_MAX_TOKENS: int = 50
    
    # Content Generation Settings
    UNIFIED_ANALYSIS_MIN_WORDS: int = 800
    UNIFIED_ANALYSIS_MAX_WORDS: int = 1200
    UNIFIED_ANALYSIS_TARGET_WORDS: int = 1000
    
    # Smart Markup Settings
    ENABLE_SMART_MARKUP: bool = True
    MAX_MARKUP_DENSITY: float = 0.15
    MARKUP_TYPES: List[str] = ["number", "concept", "positive", "negative", "insight"]
    
    # Enhanced text extraction and AI processing
    ENHANCED_EXTRACTION_ENABLED: bool = True
    ENHANCED_DATA_MARKING: bool = True
    
    # ==================== FMP API CONFIGURATION ====================
    # Financial Modeling Prep API
    FMP_API_KEY: str
    FMP_API_VERSION: str = "v3"
    FMP_BASE_URL: str = "https://financialmodelingprep.com/api"
    FMP_ENABLE: bool = True
    FMP_CACHE_TTL: int = 3600
    
    # ✅ UPDATED: Analyst Expectations (保留但不再直接用于 AI prompt)
    # Note: FMP analyst data still used for company enrichment, but not for AI analysis
    ENABLE_EXPECTATIONS_COMPARISON: bool = False  # Disabled: AI will search for analyst data instead
    EXPECTATIONS_CACHE_TTL: int = 86400
    
    # Performance Optimization
    ENABLE_UNIFIED_PROCESSING: bool = True
    LEGACY_PROCESSING_FALLBACK: bool = True
    
    # Feature flags
    ENABLE_IPO_SCANNING: bool = True
    ENABLE_AUTO_PROCESSING: bool = True
    ENABLE_SCHEDULER: bool = True
    
    # Logging settings
    LOG_LEVEL: str = "INFO"
    LOG_FILE_PATH: str = "logs/hermespeed.log"
    LOG_MAX_SIZE_MB: int = 100
    LOG_BACKUP_COUNT: int = 5
    
    # API settings
    API_RATE_LIMIT_PER_MINUTE: int = 60
    
    # ==================== ENVIRONMENT-SPECIFIC CONFIGURATIONS ====================
    
    @property
    def API_CORS_ORIGINS(self) -> List[str]:
        """Dynamic CORS configuration based on environment"""
        if self.ENVIRONMENT == "development":
            return [
                "http://localhost:3000",
                "http://localhost:8000", 
                "http://localhost:8080",
                "http://localhost:8081",
                "http://localhost:19006",  # Expo web
                "exp://192.168.1.100:19000",  # Expo development
                "exp://192.168.1.101:19000",
            ]
        elif self.ENVIRONMENT == "staging":
            return [
                "https://staging.hermespeed.com",
                "https://hermespeed-staging.vercel.app",
                "exp://staging-exp.hermespeed.com",
            ]
        elif self.ENVIRONMENT == "production":
            return [
                "https://hermespeed.com",
                "https://www.hermespeed.com", 
                "https://hermespeed.vercel.app",
                "https://app.hermespeed.com",
                "http://localhost:8081",
                "http://localhost:8080",
            ]
        else:
            return []
    
    @property 
    def ALLOW_MOCK_ENDPOINTS(self) -> bool:
        """Allow Mock endpoints only in development and staging"""
        return self.ENVIRONMENT in ["development", "staging"]
    
    @property
    def APPLE_USE_SANDBOX_AUTO(self) -> bool:
        """Auto-detect sandbox based on environment"""
        return self.ENVIRONMENT in ["development", "staging"]
    
    # ==================== PRODUCTION SAFETY ENHANCEMENTS ====================
    
    @property
    def is_production_ready(self) -> bool:
        """Check if configuration is production ready"""
        if not self.is_production:
            return True  # Development is always ready
        
        # Production checks
        missing_configs = []
        
        if not self.APPLE_SHARED_SECRET:
            missing_configs.append("APPLE_SHARED_SECRET")
        
        if not any([
            self.GOOGLE_SERVICE_ACCOUNT_KEY_PATH,
            self.GOOGLE_SERVICE_ACCOUNT_KEY_BASE64,
            self.GOOGLE_SERVICE_ACCOUNT_KEY_JSON
        ]):
            missing_configs.append("GOOGLE_SERVICE_ACCOUNT_KEY")
        
        if not self.WEBHOOK_BASE_URL:
            missing_configs.append("WEBHOOK_BASE_URL")
        
        if missing_configs:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Production environment missing configurations: {missing_configs}")
            return False
        
        return True
    
    @property
    def security_level(self) -> str:
        """Get current security level"""
        if self.is_production:
            return "HIGH" if self.is_production_ready else "MEDIUM"
        elif self.ENVIRONMENT == "staging":
            return "MEDIUM"
        else:
            return "LOW"
    
    @property
    def payment_verification_required(self) -> bool:
        """Whether payment verification is required"""
        return not self.ENABLE_MOCK_PAYMENTS
    
    # ==================== HELPER METHODS ====================
    
    @property
    def current_monthly_price(self) -> float:
        """Get current effective monthly price"""
        return self.DISCOUNTED_MONTHLY_PRICE if self.USE_DISCOUNTED_PRICING else self.STANDARD_MONTHLY_PRICE
    
    @property
    def is_discounted_pricing(self) -> bool:
        """Whether using discounted pricing"""
        return self.USE_DISCOUNTED_PRICING
    
    @property
    def email_from_address(self) -> str:
        """Get email sender address"""
        return self.EMAIL_FROM_ADDRESS or self.SMTP_USER or "noreply@hermespeed.com"
    
    def get_pricing_info(self) -> dict:
        """Get current pricing information - Monthly only"""
        monthly_price = self.current_monthly_price
        
        return {
            "monthly_price": monthly_price,
            "is_discounted": self.is_discounted_pricing,
            "pricing_type": "discounted" if self.is_discounted_pricing else "standard",
            "currency": "USD"
        }
    
    def get_frontend_verification_url(self, token: str) -> str:
        """Get email verification frontend URL"""
        return f"{self.FRONTEND_URL}/verify-email?token={token}"
    
    def get_frontend_password_reset_url(self, token: str) -> str:
        """Get password reset frontend URL"""
        return f"{self.FRONTEND_URL}/reset-password?token={token}"
    
    def get_apple_product_ids(self) -> dict:
        """Get Apple product IDs - returns both for reference"""
        return {
            "discounted": self.APPLE_MONTHLY_PRODUCT_ID_DISCOUNTED,
            "standard": self.APPLE_MONTHLY_PRODUCT_ID_STANDARD,
            "active": self.APPLE_MONTHLY_PRODUCT_ID  # Current active based on flag
        }
        return {
            "monthly": self.APPLE_MONTHLY_PRODUCT_ID,
            "yearly": self.APPLE_YEARLY_PRODUCT_ID
        }
    
    def get_google_product_ids(self) -> dict:
        """Get Google product IDs"""
        return {
            "monthly": self.GOOGLE_MONTHLY_PRODUCT_ID,
            "yearly": self.GOOGLE_YEARLY_PRODUCT_ID
        }
    
    def get_webhook_urls(self) -> dict:
        """Get webhook URLs"""
        base_url = self.WEBHOOK_BASE_URL or "https://api.hermespeed.com"
        return {
            "apple": f"{base_url}{self.APPLE_WEBHOOK_PATH}",
            "google": f"{base_url}{self.GOOGLE_WEBHOOK_PATH}"
        }
    
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.ENVIRONMENT == "development"
    
    @property
    def is_staging(self) -> bool:
        """Check if running in staging"""
        return self.ENVIRONMENT == "staging"
    
    def get_environment_info(self) -> dict:
        """Get comprehensive environment information"""
        return {
            "environment": self.ENVIRONMENT,
            "security_level": self.security_level,
            "production_ready": self.is_production_ready,
            "mock_payments_enabled": self.ENABLE_MOCK_PAYMENTS,
            "apple_sandbox": self.APPLE_USE_SANDBOX_AUTO,
            "subscription_enabled": self.ENABLE_SUBSCRIPTION,
            "current_pricing": self.get_pricing_info(),
            "apple_products": self.get_apple_product_ids(),
            "google_products": self.get_google_product_ids(),
            "webhook_urls": self.get_webhook_urls() if self.WEBHOOK_BASE_URL else None,
            "ai_model": self.AI_MODEL,  # Shows: o3-mini
            "web_search_enabled": self.WEB_SEARCH_ENABLED  # Shows: True
        }
    
    def validate_production_config(self) -> List[str]:
        """Validate production configuration and return any issues"""
        issues = []
        
        if self.is_production:
            if not self.APPLE_SHARED_SECRET:
                issues.append("Apple Shared Secret not configured")
            
            if not any([
                self.GOOGLE_SERVICE_ACCOUNT_KEY_PATH,
                self.GOOGLE_SERVICE_ACCOUNT_KEY_BASE64,
                self.GOOGLE_SERVICE_ACCOUNT_KEY_JSON
            ]):
                issues.append("Google Service Account Key not configured")
            
            if not self.WEBHOOK_BASE_URL:
                issues.append("Webhook base URL not configured")
            
            if self.APPLE_USE_SANDBOX:
                issues.append("Apple sandbox mode enabled in production")
            
            if self.ENABLE_MOCK_PAYMENTS:
                issues.append("Mock payments would be enabled (this should not happen)")
        
        return issues
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"

# Create settings instance
settings = Settings()

# ==================== RAILWAY DEPLOYMENT SUPPORT ====================
# Auto-detect Railway environment and override database/redis URLs

# Railway sets RAILWAY_ENVIRONMENT variable
IS_RAILWAY = os.getenv("RAILWAY_ENVIRONMENT") is not None

if IS_RAILWAY:
    # Railway provides DATABASE_URL and REDIS_URL as environment variables
    railway_db_url = os.getenv("DATABASE_URL")
    railway_redis_url = os.getenv("REDIS_URL")
    
    if railway_db_url:
        settings.DATABASE_URL = railway_db_url
    
    if railway_redis_url:
        settings.REDIS_URL = railway_redis_url
        settings.CELERY_BROKER_URL = railway_redis_url
        settings.CELERY_RESULT_BACKEND = railway_redis_url
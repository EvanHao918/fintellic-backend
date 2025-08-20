from pydantic_settings import BaseSettings
from typing import Optional, List
import os

class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    
    # API
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Fintellic"
    
    # Database
    DATABASE_URL: str
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
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
    
    # ==================== SUBSCRIPTION SETTINGS ====================
    # Pricing Configuration
    EARLY_BIRD_LIMIT: int = 10000  # 前10,000名用户享受早鸟价
    EARLY_BIRD_MONTHLY_PRICE: float = 39.00  # 早鸟月付价格
    EARLY_BIRD_YEARLY_PRICE: float = 280.80  # 早鸟年付价格 (39 * 12 * 0.6)
    STANDARD_MONTHLY_PRICE: float = 49.00  # 标准月付价格
    STANDARD_YEARLY_PRICE: float = 352.80  # 标准年付价格 (49 * 12 * 0.6)
    YEARLY_DISCOUNT: float = 0.6  # 年付折扣 (60% of yearly)
    
    # Payment Configuration
    STRIPE_API_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    
    # ==================== APPLE IN-APP PURCHASE ====================
    # Apple IAP Basic Configuration
    APPLE_SHARED_SECRET: Optional[str] = None
    APPLE_SANDBOX: bool = True  # Use sandbox for development
    APPLE_BUNDLE_ID: Optional[str] = None  # com.fintellic.app
    APPLE_USE_SANDBOX: bool = True  # Use sandbox environment
    
    # Apple IAP URLs
    APPLE_VERIFY_RECEIPT_URL: str = "https://buy.itunes.apple.com/verifyReceipt"
    APPLE_SANDBOX_VERIFY_URL: str = "https://sandbox.itunes.apple.com/verifyReceipt"
    
    # Apple Product IDs
    APPLE_MONTHLY_PRODUCT_ID: Optional[str] = None  # com.fintellic.app.monthly
    APPLE_YEARLY_PRODUCT_ID: Optional[str] = None  # com.fintellic.app.yearly
    
    # ==================== GOOGLE PLAY BILLING ====================
    # Google Play Basic Configuration
    GOOGLE_PLAY_SERVICE_ACCOUNT_KEY: Optional[str] = None
    GOOGLE_PLAY_PACKAGE_NAME: Optional[str] = None
    GOOGLE_PACKAGE_NAME: Optional[str] = None  # Alias for GOOGLE_PLAY_PACKAGE_NAME
    
    # Google Service Account
    GOOGLE_SERVICE_ACCOUNT_KEY_PATH: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_KEY_BASE64: Optional[str] = None  # Alternative: base64 encoded
    
    # Google Product IDs
    GOOGLE_MONTHLY_PRODUCT_ID: Optional[str] = None  # monthly_subscription
    GOOGLE_YEARLY_PRODUCT_ID: Optional[str] = None  # yearly_subscription
    
    # ==================== WEBHOOK CONFIGURATION ====================
    # Webhook URLs
    WEBHOOK_BASE_URL: Optional[str] = None  # https://api.fintellic.com
    APPLE_WEBHOOK_PATH: str = "/api/webhooks/apple"
    GOOGLE_WEBHOOK_PATH: str = "/api/webhooks/google"
    
    # ==================== FIREBASE PUSH NOTIFICATIONS (PHASE 4) ====================
    # Firebase Configuration
    FIREBASE_ENABLED: bool = True  # 启用推送通知
    FIREBASE_SERVICE_ACCOUNT_KEY: Optional[str] = None  # Firebase服务账号JSON字符串
    FIREBASE_SERVICE_ACCOUNT_PATH: Optional[str] = None  # 或者使用文件路径
    
    # FCM Settings
    FCM_SERVER_KEY: Optional[str] = None  # FCM服务器密钥（旧版，可选）
    FCM_SENDER_ID: Optional[str] = None  # FCM发送者ID
    
    # Notification Settings
    NOTIFICATION_BATCH_SIZE: int = 500  # 批量发送通知的大小
    NOTIFICATION_RATE_LIMIT: int = 100  # 每秒发送通知数量限制
    NOTIFICATION_RETRY_ATTEMPTS: int = 3  # 失败重试次数
    NOTIFICATION_RETRY_DELAY: int = 5  # 重试延迟（秒）
    
    # Notification Content Defaults
    NOTIFICATION_DEFAULT_ICON: str = "ic_notification"  # Android通知图标
    NOTIFICATION_DEFAULT_COLOR: str = "#E88B00"  # 品牌色（橙色）
    NOTIFICATION_DEFAULT_SOUND: str = "default"  # 通知声音
    
    # Notification Features
    ENABLE_FILING_NOTIFICATIONS: bool = True  # 财报发布通知
    ENABLE_DAILY_RESET_NOTIFICATIONS: bool = True  # 每日重置通知
    ENABLE_SUBSCRIPTION_NOTIFICATIONS: bool = True  # 订阅相关通知
    ENABLE_MARKET_SUMMARY_NOTIFICATIONS: bool = False  # 市场汇总通知（暂未实现）
    
    # Daily Reset Time (EST)
    DAILY_RESET_HOUR: int = 0  # EST时区的重置时间（0点）
    DAILY_RESET_MINUTE: int = 0
    
    # Test Mode
    ENABLE_TEST_NOTIFICATIONS: bool = True  # 允许发送测试通知
    TEST_NOTIFICATION_USER_IDS: List[int] = []  # 允许接收测试通知的用户ID列表
    # ================================================================
    
    # ==================== SUBSCRIPTION FEATURES ====================
    # Subscription Features
    ENABLE_SUBSCRIPTION: bool = True
    ENABLE_TRIAL_PERIOD: bool = False  # 暂不启用试用期
    TRIAL_PERIOD_DAYS: int = 7
    GRACE_PERIOD_DAYS: int = 3  # 支付失败后的宽限期
    
    # Subscription Notifications
    SUBSCRIPTION_EXPIRY_REMINDER_DAYS: List[int] = [7, 3, 1]  # 到期前提醒天数
    ENABLE_SUBSCRIPTION_EMAILS: bool = True
    
    # Early Bird Marketing
    SHOW_EARLY_BIRD_COUNTDOWN: bool = True  # 显示早鸟倒计时
    EARLY_BIRD_MARKETING_MESSAGE: str = "🔥 Limited Early Bird Offer: Only {slots} spots left!"
    
    # ==================== EMAIL NOTIFICATIONS (OPTIONAL) ====================
    # SMTP Configuration (for future use)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    NOTIFICATION_EMAIL: Optional[str] = None
    # ================================================================
    
    # Scheduler settings
    SCHEDULER_INTERVAL_MINUTES: int = 1
    FILING_LOOKBACK_MINUTES: int = 2
    
    # Processing settings
    MAX_CONCURRENT_DOWNLOADS: int = 3
    MAX_CONCURRENT_AI_TASKS: int = 2
    AI_MODEL: str = "gpt-4o-mini"
    AI_MAX_TOKENS: int = 16000
    
    # ==================== NEW AI OPTIMIZATION SETTINGS ====================
    # AI Generation Parameters
    AI_TEMPERATURE: float = 0.3  # 降低temperature以获得更稳定的输出
    AI_UNIFIED_ANALYSIS_MAX_TOKENS: int = 2000  # 统一分析的最大token数
    AI_FEED_SUMMARY_MAX_TOKENS: int = 50  # Feed摘要的最大token数
    
    # Content Generation Settings
    UNIFIED_ANALYSIS_MIN_WORDS: int = 800
    UNIFIED_ANALYSIS_MAX_WORDS: int = 1200
    UNIFIED_ANALYSIS_TARGET_WORDS: int = 1000
    
    # Smart Markup Settings
    ENABLE_SMART_MARKUP: bool = True
    MAX_MARKUP_DENSITY: float = 0.15  # 最多15%的文本被标记
    MARKUP_TYPES: List[str] = ["number", "concept", "positive", "negative", "insight"]
    
    # ==================== ENHANCED ACCURACY SETTINGS ====================
    # Enhanced text extraction and AI processing for better financial data accuracy
    ENHANCED_EXTRACTION_ENABLED: bool = True    # 启用增强文本提取（Markdown表格）
    ENHANCED_DATA_MARKING: bool = True          # 启用严格数据标记验证
    # ================================================================
    
    # ==================== FMP API CONFIGURATION ====================
    # Financial Modeling Prep API
    FMP_API_KEY: str
    FMP_API_VERSION: str = "v3"
    FMP_BASE_URL: str = "https://financialmodelingprep.com/api"
    FMP_ENABLE: bool = True
    FMP_CACHE_TTL: int = 3600  # 1 hour cache
    
    # Analyst Expectations API (now using FMP)
    ENABLE_EXPECTATIONS_COMPARISON: bool = True  # Re-enabled with FMP
    EXPECTATIONS_CACHE_TTL: int = 86400  # 24 hours
    # ================================================================
    
    # Performance Optimization
    ENABLE_UNIFIED_PROCESSING: bool = True  # 启用统一处理模式
    LEGACY_PROCESSING_FALLBACK: bool = True  # 保持向后兼容
    
    # ========================================================================
    
    # Feature flags
    ENABLE_IPO_SCANNING: bool = True
    ENABLE_AUTO_PROCESSING: bool = True
    ENABLE_SCHEDULER: bool = True
    
    # Logging settings
    LOG_LEVEL: str = "INFO"
    LOG_FILE_PATH: str = "logs/fintellic.log"
    LOG_MAX_SIZE_MB: int = 100
    LOG_BACKUP_COUNT: int = 5
    
    # API settings
    API_RATE_LIMIT_PER_MINUTE: int = 60
    API_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create settings instance
settings = Settings()
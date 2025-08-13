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
    
    # Apple In-App Purchase
    APPLE_SHARED_SECRET: Optional[str] = None
    APPLE_SANDBOX: bool = True  # Use sandbox for development
    
    # Google Play Billing
    GOOGLE_PLAY_SERVICE_ACCOUNT_KEY: Optional[str] = None
    GOOGLE_PLAY_PACKAGE_NAME: Optional[str] = None
    
    # Subscription Features
    ENABLE_SUBSCRIPTION: bool = True
    ENABLE_TRIAL_PERIOD: bool = False  # 暂不启用试用期
    TRIAL_PERIOD_DAYS: int = 7
    GRACE_PERIOD_DAYS: int = 3  # 支付失败后的宽限期
    
    # Subscription Notifications
    SUBSCRIPTION_EXPIRY_REMINDER_DAYS: List[int] = [7, 3, 1]  # 到期前提醒天数
    ENABLE_SUBSCRIPTION_EMAILS: bool = True
    
    # Early Bird Marketing
    SHOW_EARLY_BIRD_COUNTDOWN: bool = True  # 显示早鸟名额倒计时
    EARLY_BIRD_MARKETING_MESSAGE: str = "🔥 Limited Early Bird Offer: Only {slots} spots left!"
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
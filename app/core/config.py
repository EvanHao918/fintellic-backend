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
    
    # Scheduler settings
    SCHEDULER_INTERVAL_MINUTES: int = 1
    FILING_LOOKBACK_MINUTES: int = 2
    
    # Processing settings
    MAX_CONCURRENT_DOWNLOADS: int = 3
    MAX_CONCURRENT_AI_TASKS: int = 2
    AI_MODEL: str = "gpt-4o-mini"
    AI_MAX_TOKENS: int = 16000
    
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
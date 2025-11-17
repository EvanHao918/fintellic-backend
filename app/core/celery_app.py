# app/core/celery_app.py
"""
Celery configuration for async task processing
"""
import os
from celery import Celery

# Fix macOS fork issue
os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'

# CRITICAL FIX: Read REDIS_URL directly from environment variable
# This ensures we use Railway's Redis URL, not the default from settings
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery instance
celery_app = Celery(
    "fintellic",
    broker=redis_url,
    backend=redis_url,
    include=["app.tasks.filing_tasks"]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task settings
    task_soft_time_limit=300,  # 5 minutes soft limit
    task_time_limit=600,  # 10 minutes hard limit
    
    # Worker settings for thread safety
    worker_prefetch_multiplier=1,  # Important for thread pool
    task_acks_late=True,  # Acknowledge task after completion
    task_reject_on_worker_lost=True,  # Requeue tasks if worker dies
    
    # Rate limiting for OpenAI API
    task_annotations={
        "app.tasks.filing_tasks.process_filing_task": {
            "rate_limit": "10/m"  # 10 tasks per minute
        }
    }
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

# Import routers
from app.api.api import api_router
# Import scheduler
from app.services.scheduler import filing_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up Fintellic API...")
    
    # Start the filing scheduler
    await filing_scheduler.start()
    logger.info("Filing scheduler started - scanning every 5 minutes")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Fintellic API...")
    
    # Stop the filing scheduler
    await filing_scheduler.stop()
    logger.info("Filing scheduler stopped")

# Create FastAPI app
app = FastAPI(
    title="Fintellic API",
    description="AI-powered financial intelligence platform",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS with specific settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8081",
        "http://localhost:8080",
        "http://localhost:19006",  # Expo web
        "exp://192.168.1.*",        # Expo development
        "*"  # Allow all origins in development
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Welcome to Fintellic API",
        "version": "1.0.0",
        "status": "operational",
        "scanner": "active" if filing_scheduler.is_running else "inactive"
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "fintellic-api",
        "scanner_running": filing_scheduler.is_running
    }

# Manual scan endpoint (for testing)
@app.post("/api/v1/scan/trigger")
async def trigger_scan():
    """Manually trigger a filing scan (for testing)"""
    logger.info("Manual scan triggered")
    new_filings = await filing_scheduler.run_single_scan()
    return {
        "status": "scan_completed",
        "new_filings_count": len(new_filings),
        "filings": new_filings
    }

# Include API router
app.include_router(api_router, prefix="/api/v1")
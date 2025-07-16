from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import traceback

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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Add global exception handler to ensure CORS headers are included in error responses
@app.exception_handler(Exception)
async def universal_exception_handler(request: Request, exc: Exception):
    """Handle all exceptions and ensure CORS headers are included"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    # Get detailed error information for debugging
    error_detail = str(exc)
    error_type = type(exc).__name__
    
    # In development, include more detailed error information
    if app.debug or logger.level <= logging.DEBUG:
        error_trace = traceback.format_exc()
        logger.error(f"Traceback:\n{error_trace}")
    
    # Return JSON response with CORS headers
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": error_type,
            "message": error_detail if app.debug else "An error occurred processing your request"
        },
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*",
        }
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
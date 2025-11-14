from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging

# Import routers
from app.api.api import api_router
# Import scheduler
from app.services.scheduler import filing_scheduler
# Import settings for secure CORS
from app.core.config import settings

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

# Configure CORS with security-enhanced settings
cors_origins = settings.API_CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

logger.info(f"CORS configured for environment: {settings.ENVIRONMENT}")
logger.info(f"Allowed origins: {cors_origins}")

# Add custom exception handler to ensure CORS headers are always added
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler that ensures CORS headers are added to error responses
    """
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    # Create error response
    response = JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
    
    # Add CORS headers manually for error responses
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    
    return response

# Add specific handler for authentication errors
@app.exception_handler(401)
async def unauthorized_exception_handler(request: Request, exc):
    """
    Handle 401 errors with proper CORS headers
    """
    response = JSONResponse(
        status_code=401,
        content={"detail": "Not authenticated"}
    )
    
    # Add CORS headers
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    
    return response

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Welcome to Fintellic API",
        "version": "1.0.0",
        "status": "operational",
        "scanner": "active" if filing_scheduler.is_running else "inactive",
        "environment": settings.ENVIRONMENT
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "fintellic-api",
        "scanner_running": filing_scheduler.is_running,
        "email_verification_enabled": settings.ENABLE_EMAIL_VERIFICATION,
        "password_reset_enabled": settings.ENABLE_PASSWORD_RESET
    }

# Manual scan endpoint (for testing)
@app.post("/api/v1/scan/trigger")
async def trigger_scan():
    """Manually trigger a filing scan (for testing)"""
    if not settings.ALLOW_MOCK_ENDPOINTS:
        return {"error": "Mock endpoints not allowed in this environment"}
    
    logger.info("Manual scan triggered")
    new_filings = await filing_scheduler.run_single_scan()
    return {
        "status": "scan_completed",
        "new_filings_count": len(new_filings),
        "filings": new_filings
    }

# Include API router
app.include_router(api_router, prefix="/api/v1")
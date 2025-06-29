"""
Main API router that combines all endpoint routers
"""
from fastapi import APIRouter

from app.api.endpoints import auth, users, filings, companies, interactions

api_router = APIRouter()

# Authentication endpoints
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])

# User endpoints
api_router.include_router(users.router, prefix="/users", tags=["users"])

# Filing endpoints
api_router.include_router(filings.router, prefix="/filings", tags=["filings"])

# Company endpoints
api_router.include_router(companies.router, prefix="/companies", tags=["companies"])

# Interaction endpoints (votes, comments, watchlist)
api_router.include_router(interactions.router, prefix="", tags=["interactions"])
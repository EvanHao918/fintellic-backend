# app/api/api.py
"""
Main API router that combines all endpoint routers
"""
from fastapi import APIRouter

from app.api.endpoints import auth, users, filings, companies, interactions, stats, earnings, comments, watchlist

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

# Comment endpoints (Day 10.5 addition)
api_router.include_router(comments.router, prefix="", tags=["comments"])

# Statistics endpoints (Day 8 addition)
api_router.include_router(stats.router, prefix="/stats", tags=["statistics"])

# Earnings calendar endpoints (Day 8 addition)
api_router.include_router(earnings.router, prefix="/earnings", tags=["earnings"])

# Watchlist endpoints
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["watchlist"])
"""
Filing-related API endpoints - Correct version based on actual models
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from app.api import deps
from app.core.database import get_db
from app.models.filing import Filing
from app.models.company import Company

router = APIRouter()


@router.get("/test")
async def test_endpoint(
    db: Session = Depends(get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Test endpoint to verify auth is working
    """
    return {
        "message": "Auth is working!",
        "user_id": current_user.id,
        "username": current_user.username
    }


@router.get("/")
async def get_filings(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    filing_type: Optional[str] = Query(None, description="Filter by filing type (10-K, 10-Q, 8-K)"),
    ticker: Optional[str] = Query(None, description="Filter by company ticker"),
    db: Session = Depends(get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Get list of filings with pagination and filters
    """
    try:
        # Build query with company join
        query = db.query(Filing).options(joinedload(Filing.company))
        
        # Apply filters
        if filing_type:
            query = query.filter(Filing.filing_type == filing_type)
            
        # Filter by ticker if provided
        if ticker:
            query = query.join(Company).filter(Company.ticker == ticker.upper())
        
        # Only show completed filings
        query = query.filter(Filing.status == "completed")
        
        # Order by filing date descending
        query = query.order_by(desc(Filing.filing_date))
        
        # Get total count
        total = query.count()
        
        # Get paginated results
        filings = query.offset(skip).limit(limit).all()
        
        # Format response
        filing_list = []
        for filing in filings:
            filing_dict = {
                "id": filing.id,
                "form_type": filing.filing_type,
                "filing_date": filing.filing_date.isoformat() if filing.filing_date else None,
                "accession_number": filing.accession_number,
                "file_url": filing.primary_doc_url,
                "one_liner": filing.ai_summary[:100] + "..." if filing.ai_summary and len(filing.ai_summary) > 100 else filing.ai_summary,
                "sentiment": filing.management_tone,
                "tags": filing.key_tags or [],
                "vote_counts": {
                    "bullish": filing.bullish_votes or 0,
                    "neutral": filing.neutral_votes or 0,
                    "bearish": filing.bearish_votes or 0
                },
                "company": {
                    "ticker": filing.company.ticker if filing.company else "Unknown",
                    "name": filing.company.name if filing.company else "Unknown Company",
                    "cik": filing.company.cik if filing.company else "Unknown"
                } if filing.company else None
            }
            filing_list.append(filing_dict)
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "data": filing_list
        }
        
    except Exception as e:
        # Log the error for debugging
        print(f"Error in get_filings: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{filing_id}")
async def get_filing_detail(
    filing_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Get detailed information about a specific filing
    """
    try:
        # Get filing with company data
        filing = db.query(Filing).options(joinedload(Filing.company)).filter(
            Filing.id == filing_id,
            Filing.status == "completed"
        ).first()
        
        if not filing:
            raise HTTPException(status_code=404, detail="Filing not found")
        
        # Build response
        response = {
            "id": filing.id,
            "cik": filing.company.cik if filing.company else "Unknown",
            "form_type": filing.filing_type,
            "filing_date": filing.filing_date.isoformat() if filing.filing_date else None,
            "accession_number": filing.accession_number,
            "file_url": filing.primary_doc_url,
            "full_text_url": filing.full_text_url,
            "status": filing.status,
            
            # AI-generated content
            "ai_summary": filing.ai_summary,
            "management_tone": filing.management_tone,
            "tone_explanation": filing.tone_explanation,
            "key_questions": filing.key_questions or [],
            "key_quotes": filing.key_quotes or [],
            "key_tags": filing.key_tags or [],
            
            # Financial data
            "financial_highlights": filing.financial_highlights,
            
            # Voting data
            "vote_counts": {
                "bullish": filing.bullish_votes or 0,
                "neutral": filing.neutral_votes or 0,
                "bearish": filing.bearish_votes or 0
            },
            
            # Timestamps
            "processing_started_at": filing.processing_started_at.isoformat() if filing.processing_started_at else None,
            "processing_completed_at": filing.processing_completed_at.isoformat() if filing.processing_completed_at else None,
            "created_at": filing.created_at.isoformat(),
            "updated_at": filing.updated_at.isoformat(),
            
            # Company information
            "company": {
                "ticker": filing.company.ticker,
                "name": filing.company.name,
                "cik": filing.company.cik,
                "sector": filing.company.sic_description,
                "exchange": filing.company.exchange,
                "is_sp500": filing.company.is_sp500,
                "is_nasdaq100": filing.company.is_nasdaq100
            } if filing.company else None
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_filing_detail: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
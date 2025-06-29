"""
Company-related API endpoints - Fixed version
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, desc

from app.api import deps
from app.core.database import get_db
from app.models.company import Company
from app.models.filing import Filing

router = APIRouter()


@router.get("/")
async def get_companies(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(50, ge=1, le=100, description="Number of items to return"),
    search: Optional[str] = Query(None, description="Search by name or ticker"),
    db: Session = Depends(get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Get list of S&P 500 companies
    """
    try:
        # Build query
        query = db.query(Company)
        
        # Apply search filter
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Company.ticker.ilike(search_term),
                    Company.name.ilike(search_term)
                )
            )
        
        # Order by ticker
        query = query.order_by(Company.ticker)
        
        # Get total count
        total = query.count()
        
        # Get paginated results
        companies = query.offset(skip).limit(limit).all()
        
        # Format response
        company_list = []
        for company in companies:
            company_dict = {
                "ticker": company.ticker,
                "name": company.name,
                "cik": company.cik,
                "sector": company.sic_description,
                "exchange": company.exchange,
                "is_sp500": company.is_sp500,
                "is_nasdaq100": company.is_nasdaq100
            }
            company_list.append(company_dict)
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "data": company_list
        }
        
    except Exception as e:
        print(f"Error in get_companies: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}")
async def get_company_detail(
    ticker: str,
    db: Session = Depends(get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Get detailed information about a specific company
    """
    try:
        company = db.query(Company).filter(
            Company.ticker == ticker.upper()
        ).first()
        
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        
        # Get recent filings count
        recent_filings_count = db.query(Filing).filter(
            Filing.company_id == company.id,
            Filing.status == "completed"
        ).count()
        
        # Helper function to safely get datetime string
        def safe_datetime(dt):
            return dt.isoformat() if dt else None
        
        # Build response with safe attribute access
        response = {
            "ticker": company.ticker,
            "name": company.name,
            "cik": company.cik,
            "legal_name": getattr(company, 'legal_name', None),
            "sector": getattr(company, 'sic_description', None),
            "sic": getattr(company, 'sic', None),
            "exchange": getattr(company, 'exchange', None),
            "state": getattr(company, 'state', None),
            "state_of_incorporation": getattr(company, 'state_of_incorporation', None),
            "fiscal_year_end": getattr(company, 'fiscal_year_end', None),
            "business_phone": getattr(company, 'business_phone', None),
            "business_address": getattr(company, 'business_address', None),
            "mailing_address": getattr(company, 'mailing_address', None),
            "is_sp500": getattr(company, 'is_sp500', False),
            "is_nasdaq100": getattr(company, 'is_nasdaq100', False),
            "is_active": getattr(company, 'is_active', True),
            "last_filing_date": safe_datetime(getattr(company, 'last_filing_date', None)),
            "total_filings": recent_filings_count,
            "created_at": safe_datetime(getattr(company, 'created_at', None)),
            "updated_at": safe_datetime(getattr(company, 'updated_at', None))
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_company_detail: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/filings")
async def get_company_filings(
    ticker: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    filing_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Get filings for a specific company
    """
    try:
        # First check if company exists
        company = db.query(Company).filter(
            Company.ticker == ticker.upper()
        ).first()
        
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        
        # Build query for filings
        query = db.query(Filing).filter(
            Filing.company_id == company.id,
            Filing.status == "completed"
        )
        
        # Apply filing type filter
        if filing_type:
            query = query.filter(Filing.filing_type == filing_type)
        
        # Order by date
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
                }
            }
            filing_list.append(filing_dict)
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "company": {
                "ticker": company.ticker,
                "name": company.name,
                "cik": company.cik
            },
            "data": filing_list
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_company_filings: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
"""
Company-related API endpoints - Enhanced with FMP integration
FIXED: Changed file_url to filing_url for consistency
FIXED: Updated to handle both primary_document_url and primary_doc_url fields
ENHANCED: Added FMP company profile fetching for detailed company info
"""
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, desc
import logging

from app.api import deps
from app.core.database import get_db
from app.core.cache import cache
from app.models.company import Company
from app.models.filing import Filing
from app.services.fmp_service import fmp_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/")
async def get_companies(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(50, ge=1, le=100, description="Number of items to return"),
    search: Optional[str] = Query(None, description="Search by name or ticker"),
    db: Session = Depends(get_db),
    current_user = Depends(deps.get_current_user_optional)  # 改为可选认证
):
    """
    Get list of S&P 500 companies
    Public endpoint - no authentication required
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
    include_fmp_data: bool = Query(False, description="Include data from FMP API"),
    db: Session = Depends(get_db),
    current_user = Depends(deps.get_current_user_optional)  # 改为可选认证
):
    """
    Get detailed information about a specific company
    Public endpoint - no authentication required
    ENHANCED: Can fetch additional data from FMP API if requested
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
        
        # ENHANCED: Fetch additional data from FMP if requested
        if include_fmp_data:
            try:
                # Cache key for FMP enriched data
                cache_key = f"company:detail:fmp:{ticker.upper()}"
                cached_fmp_data = cache.get(cache_key)
                
                if cached_fmp_data:
                    response["fmp_data"] = cached_fmp_data
                else:
                    # Fetch from FMP
                    fmp_profile = fmp_service.get_company_profile(ticker.upper())
                    
                    if fmp_profile:
                        # Merge FMP data with database data
                        response["fmp_data"] = {
                            "sector": fmp_profile.get("sector"),
                            "industry": fmp_profile.get("industry"),
                            "headquarters": fmp_profile.get("headquarters"),
                            "country": fmp_profile.get("country"),
                            "employees": fmp_profile.get("employees"),
                            "market_cap": fmp_profile.get("market_cap"),
                            "market_cap_formatted": fmp_profile.get("market_cap_formatted"),
                            "website": fmp_profile.get("website"),
                            "description": fmp_profile.get("description"),
                            "ceo": fmp_profile.get("ceo"),
                            "price": fmp_profile.get("price"),
                            "beta": fmp_profile.get("beta"),
                            "volume_avg": fmp_profile.get("volume_avg"),
                        }
                        
                        # Update database with FMP data if it's missing
                        if not company.sector and fmp_profile.get("sector"):
                            company.sector = fmp_profile.get("sector")
                        if not company.industry and fmp_profile.get("industry"):
                            company.industry = fmp_profile.get("industry")
                        if not company.headquarters and fmp_profile.get("headquarters"):
                            company.headquarters = fmp_profile.get("headquarters")
                        if not company.employees and fmp_profile.get("employees"):
                            company.employees = fmp_profile.get("employees")
                        if not company.website and fmp_profile.get("website"):
                            company.website = fmp_profile.get("website")
                        
                        db.commit()
                        
                        # Cache for 24 hours
                        cache.set(cache_key, response["fmp_data"], ttl=86400)
                    else:
                        logger.warning(f"No FMP data available for {ticker}")
                        
            except Exception as e:
                logger.error(f"Error fetching FMP data for {ticker}: {str(e)}")
                # Continue without FMP data
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_company_detail: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/profile")
async def get_company_profile(
    ticker: str,
    db: Session = Depends(get_db),
    current_user = Depends(deps.get_current_user_optional)
):
    """
    Get enhanced company profile with FMP data
    This endpoint always tries to fetch FMP data for the most complete profile
    """
    try:
        # First get basic company data from database
        company = db.query(Company).filter(
            Company.ticker == ticker.upper()
        ).first()
        
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        
        # Build comprehensive profile
        profile = {
            "ticker": company.ticker,
            "name": company.name,
            "cik": company.cik,
            "is_sp500": company.is_sp500,
            "is_nasdaq100": company.is_nasdaq100,
            "is_public": getattr(company, 'is_public', True),
            "has_s1_filing": getattr(company, 'has_s1_filing', False)
        }
        
        # Try to get FMP data
        try:
            fmp_profile = fmp_service.get_company_profile(ticker.upper())
            if fmp_profile:
                profile.update({
                    "sector": fmp_profile.get("sector") or company.sic_description,
                    "industry": fmp_profile.get("industry") or getattr(company, 'industry', None),
                    "headquarters": fmp_profile.get("headquarters") or getattr(company, 'headquarters', None),
                    "country": fmp_profile.get("country") or getattr(company, 'country', 'United States'),
                    "employees": fmp_profile.get("employees") or getattr(company, 'employees', None),
                    "market_cap": fmp_profile.get("market_cap") or getattr(company, 'market_cap', None),
                    "market_cap_formatted": fmp_profile.get("market_cap_formatted"),
                    "exchange": company.exchange,
                    "website": fmp_profile.get("website") or getattr(company, 'website', None),
                    "description": fmp_profile.get("description"),
                    "ceo": fmp_profile.get("ceo"),
                    "founded_year": getattr(company, 'founded_year', None),
                    "fiscal_year_end": company.fiscal_year_end,
                    "state": company.state,
                    "price": fmp_profile.get("price"),
                    "beta": fmp_profile.get("beta"),
                    "volume_avg": fmp_profile.get("volume_avg"),
                })
                
                # Also get key metrics if available
                key_metrics = fmp_service.get_company_key_metrics(ticker.upper())
                if key_metrics:
                    profile["key_metrics"] = key_metrics
                    
            else:
                # Fallback to database data only
                profile.update({
                    "sector": company.sic_description,
                    "industry": getattr(company, 'industry', None),
                    "headquarters": getattr(company, 'headquarters', None),
                    "country": getattr(company, 'country', 'United States'),
                    "employees": getattr(company, 'employees', None),
                    "market_cap": getattr(company, 'market_cap', None),
                    "exchange": company.exchange,
                    "website": getattr(company, 'website', None),
                    "founded_year": getattr(company, 'founded_year', None),
                    "fiscal_year_end": company.fiscal_year_end,
                    "state": company.state,
                })
                
        except Exception as e:
            logger.error(f"Error fetching FMP data for {ticker}: {str(e)}")
            # Continue with database data only
            profile.update({
                "sector": company.sic_description,
                "industry": getattr(company, 'industry', None),
                "exchange": company.exchange,
                "fiscal_year_end": company.fiscal_year_end,
                "state": company.state,
            })
        
        # Remove None values for cleaner response
        profile = {k: v for k, v in profile.items() if v is not None}
        
        return profile
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_company_profile: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/filings")
async def get_company_filings(
    ticker: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    filing_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(deps.get_current_user_optional)  # 改为可选认证
):
    """
    Get filings for a specific company
    Public endpoint - no authentication required
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
            # FIXED: Try both fields with proper fallback chain
            # First try new field (primary_document_url), then old field (primary_doc_url), then filing_url
            filing_url = None
            
            # Try primary_document_url (new field)
            if hasattr(filing, 'primary_document_url') and filing.primary_document_url:
                filing_url = filing.primary_document_url
            # Fall back to primary_doc_url (old field)
            elif hasattr(filing, 'primary_doc_url') and filing.primary_doc_url:
                filing_url = filing.primary_doc_url
            # Finally fall back to filing_url
            elif hasattr(filing, 'filing_url') and filing.filing_url:
                filing_url = filing.filing_url
            else:
                filing_url = ""
            
            filing_dict = {
                "id": filing.id,
                "form_type": filing.filing_type,
                "filing_date": filing.filing_date.isoformat() if filing.filing_date else None,
                "accession_number": filing.accession_number,
                "filing_url": filing_url,  # Using the resolved URL
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
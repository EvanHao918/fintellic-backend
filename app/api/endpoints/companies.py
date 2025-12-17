"""
Company-related API endpoints - Enhanced with FMP integration
FIXED: Changed file_url to filing_url for consistency
FIXED: Updated to handle both primary_document_url and primary_doc_url fields
ENHANCED: Added FMP company profile fetching for detailed company info
UPDATED: Optimized to use database-stored FMP data instead of real-time API calls (FMP Optimization Project)
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
from app.models.filing import Filing, FilingType
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
    UPDATED: Prioritizes database-stored FMP data over real-time API calls
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
        
        # Build response with safe attribute access - UPDATED: Include FMP fields from database
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
            "updated_at": safe_datetime(getattr(company, 'updated_at', None)),
            
            # UPDATED: Include FMP data from database (optimization key point)
            "market_cap": getattr(company, 'market_cap', None),
            "market_cap_formatted": getattr(company, 'market_cap_formatted', None),
            "analyst_consensus": getattr(company, 'analyst_consensus', None),
            "website": getattr(company, 'website', None),
            "employees": getattr(company, 'employees', None),
            "headquarters": getattr(company, 'headquarters', None),
            "country": getattr(company, 'country', None),
            "industry": getattr(company, 'industry', None)
        }
        
        # UPDATED: Only fetch real-time FMP data if explicitly requested AND database data is incomplete
        if include_fmp_data:
            # Check if we need to fetch from FMP (database data incomplete)
            needs_fmp_fetch = (
                not company.market_cap or 
                not company.analyst_consensus or 
                not company.website
            )
            
            if needs_fmp_fetch:
                logger.info(f"[API] Database FMP data incomplete for {ticker}, fetching from FMP API")
                try:
                    # Cache key for FMP enriched data
                    cache_key = f"company:detail:fmp:{ticker.upper()}"
                    cached_fmp_data = cache.get(cache_key)
                    
                    if cached_fmp_data:
                        response["fmp_data"] = cached_fmp_data
                    else:
                        # Fetch from FMP as fallback
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
                            
                            # OPTIMIZATION: Update database with missing FMP data for future use
                            company.update_fmp_data(fmp_profile)
                            db.commit()
                            logger.info(f"[API] Updated database with FMP data for {ticker}")
                            
                            # Cache for 24 hours
                            cache.set(cache_key, response["fmp_data"], ttl=86400)
                        else:
                            logger.warning(f"No FMP data available for {ticker}")
                except Exception as fmp_error:
                    logger.error(f"[API] FMP API fallback failed for {ticker}: {str(fmp_error)}")
                    # Continue without FMP data
            else:
                logger.info(f"[API] Using complete database FMP data for {ticker}, no API call needed")
                            
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
    ENHANCED: Handles IPO companies (ticker prefix "IPO-") gracefully
    """
    try:
        ticker_upper = ticker.upper()
        
        # 🆕 Check if this is an IPO ticker (format: "IPO-{last 4 digits of CIK}")
        if ticker_upper.startswith("IPO-"):
            logger.info(f"[API] Handling IPO ticker: {ticker_upper}")
            
            # Extract last 4 digits of CIK from ticker (e.g., "IPO-3548" → "3548")
            cik_suffix = ticker_upper.replace("IPO-", "")
            
            if not cik_suffix.isdigit() or len(cik_suffix) != 4:
                raise HTTPException(status_code=404, detail="Invalid IPO ticker format")
            
            # Query company by CIK suffix (CIK ends with these 4 digits)
            # Example: CIK "0002073548" ends with "3548"
            company = db.query(Company).filter(
                Company.cik.like(f"%{cik_suffix}")
            ).first()
            
            if not company:
                raise HTTPException(
                    status_code=404, 
                    detail=f"No company found with CIK ending in {cik_suffix}"
                )
            
            # Check if this company has S-1 filings
            has_s1 = db.query(Filing).filter(
                Filing.company_id == company.id,
                Filing.filing_type == 'FORM_S1'
            ).first() is not None
            
            # Return IPO company profile
            return {
                "ticker": ticker_upper,
                "name": company.name,
                "cik": company.cik,
                "is_ipo": True,
                "ipo_status": "Pre-IPO (S-1 Filed)" if has_s1 else "Pre-IPO",
                "description": f"Pre-IPO company (CIK: {company.cik})",
                # Basic fields for compatibility
                "market_cap": None,
                "market_cap_formatted": "Pre-IPO",
                "analyst_consensus": None,
                "website": None,
                "employees": None,
                "headquarters": None,
                "country": "United States",
                "exchange": "Pending IPO",
                "sector": getattr(company, 'sector', getattr(company, 'sic_description', None)),
                "industry": getattr(company, 'industry', None),
                "founded_year": None,
                "is_sp500": False,
                "is_nasdaq100": False,
            }
        
        # First get basic company data from database (normal flow for listed companies)
        company = db.query(Company).filter(
            Company.ticker == ticker_upper
        ).first()
        
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        
        # CORE OPTIMIZATION: Build profile primarily from database-stored FMP data
        profile = {
            "ticker": company.ticker,
            "name": company.name,
            "cik": company.cik,
            "is_sp500": company.is_sp500,
            "is_nasdaq100": company.is_nasdaq100,
            "is_public": getattr(company, 'is_public', True),
            "has_s1_filing": getattr(company, 'has_s1_filing', False),
            
            # OPTIMIZED: Use database-stored FMP data (major performance improvement)
            "sector": getattr(company, 'sector', None) or company.sic_description,
            "industry": getattr(company, 'industry', None),
            "headquarters": getattr(company, 'headquarters', None),
            "country": getattr(company, 'country', 'United States'),
            "employees": getattr(company, 'employees', None),
            "market_cap": getattr(company, 'market_cap', None),
            "market_cap_formatted": getattr(company, 'market_cap_formatted', None),
            "analyst_consensus": getattr(company, 'analyst_consensus', None),
            "website": getattr(company, 'website', None),
            "exchange": company.exchange,
            "founded_year": getattr(company, 'founded_year', None),
            "fiscal_year_end": company.fiscal_year_end,
            "state": company.state,
        }
        
        # FALLBACK: Only call FMP API if critical database data is missing
        has_critical_data = company.market_cap or company.analyst_consensus or company.website
        
        if not has_critical_data:
            logger.info(f"[API] Critical data missing for {ticker}, falling back to FMP API")
            try:
                # Fetch from FMP as fallback only
                fmp_profile = fmp_service.get_company_profile(ticker.upper())
                if fmp_profile:
                    # Update profile with FMP data
                    profile.update({
                        "sector": fmp_profile.get("sector") or profile["sector"],
                        "industry": fmp_profile.get("industry") or profile["industry"],
                        "headquarters": fmp_profile.get("headquarters") or profile["headquarters"],
                        "country": fmp_profile.get("country") or profile["country"],
                        "employees": fmp_profile.get("employees") or profile["employees"],
                        "market_cap": fmp_profile.get("market_cap") or profile["market_cap"],
                        "market_cap_formatted": fmp_profile.get("market_cap_formatted"),
                        "website": fmp_profile.get("website") or profile["website"],
                        "description": fmp_profile.get("description"),
                        "ceo": fmp_profile.get("ceo"),
                        "price": fmp_profile.get("price"),
                        "beta": fmp_profile.get("beta"),
                        "volume_avg": fmp_profile.get("volume_avg"),
                    })
                    
                    # OPTIMIZATION: Update database for future use
                    company.update_fmp_data(fmp_profile)
                    db.commit()
                    logger.info(f"[API] Updated database with fallback FMP data for {ticker}")
                    
                    # Also get key metrics if available
                    try:
                        key_metrics = fmp_service.get_company_key_metrics(ticker.upper())
                        if key_metrics:
                            profile["key_metrics"] = key_metrics
                            # Update analyst consensus if missing
                            if not company.analyst_consensus:
                                analyst_consensus = fmp_service.get_analyst_consensus(ticker.upper())
                                if analyst_consensus:
                                    company.analyst_consensus = analyst_consensus
                                    db.commit()
                    except Exception as metrics_error:
                        logger.warning(f"[API] Could not fetch key metrics for {ticker}: {str(metrics_error)}")
                        
            except Exception as fmp_error:
                logger.error(f"[API] FMP API fallback failed for {ticker}: {str(fmp_error)}")
                # Continue without FMP data
        else:
            logger.info(f"[API] Using database-stored FMP data for {ticker} (OPTIMIZATION SUCCESS)")
            
            # For completeness, try to get key metrics from cache or quick call
            # This is a lighter call and provides additional context
            try:
                cache_key = f"fmp:key_metrics:{ticker.upper()}"
                cached_metrics = cache.get(cache_key)
                if cached_metrics:
                    import json
                    profile["key_metrics"] = json.loads(cached_metrics)
            except Exception as cache_error:
                logger.warning(f"[API] Could not load cached metrics for {ticker}: {str(cache_error)}")
        
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
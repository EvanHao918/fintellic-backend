# app/services/earnings_calendar_service.py
"""
Service for fetching and managing earnings calendar data
Updated to use FMP instead of yfinance
FIXED: Removed async/await to match FMP service sync implementation
"""
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
import logging

from app.models.company import Company
from app.models.earnings_calendar import EarningsCalendar, EarningsTime
from app.core.cache import cache, CACHE_TTL
from app.core.config import settings
from app.services.fmp_service import fmp_service

logger = logging.getLogger(__name__)


class EarningsCalendarService:
    """Service for managing earnings calendar data using FMP"""
    
    @staticmethod
    def fetch_earnings_calendar(
        ticker: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict]:
        """
        Fetch earnings calendar data from FMP
        FIXED: Changed from async to sync to match FMP service
        """
        try:
            # Default to next 3 months if not specified
            if not start_date:
                start_date = date.today()
            if not end_date:
                end_date = start_date + timedelta(days=90)
            
            # Get earnings data from FMP (sync call - no await)
            earnings_data = fmp_service.get_earnings_calendar(
                start_date.isoformat(),
                end_date.isoformat()
            )
            
            if not earnings_data:
                logger.warning(f"No earnings data returned from FMP for period {start_date} to {end_date}")
                return []
            
            # Filter for specific ticker
            ticker_earnings = [e for e in earnings_data if e.get('symbol') == ticker]
            
            if not ticker_earnings:
                logger.info(f"No earnings data found for {ticker} in the fetched data")
                return []
            
            # Convert to expected format
            results = []
            for item in ticker_earnings:
                # Parse date and time
                earnings_date_str = item.get('date', '')
                earnings_time_str = item.get('time', 'TNS').upper()
                
                # Convert time to enum
                if earnings_time_str == 'BMO':
                    earnings_time = EarningsTime.BMO
                elif earnings_time_str == 'AMC':
                    earnings_time = EarningsTime.AMC
                else:
                    earnings_time = EarningsTime.TNS
                
                # Parse date
                try:
                    earnings_date = datetime.strptime(earnings_date_str, '%Y-%m-%d').date()
                except Exception as e:
                    logger.warning(f"Failed to parse date {earnings_date_str}: {e}")
                    continue
                
                results.append({
                    "earnings_date": earnings_date,
                    "earnings_time": earnings_time,
                    "eps_estimate": item.get('epsEstimated'),
                    "revenue_estimate": item.get('revenueEstimated'),
                    "fiscal_quarter": item.get('fiscalDateEnding', ''),
                    "fiscal_year": earnings_date.year
                })
            
            logger.info(f"Found {len(results)} earnings entries for {ticker}")
            return results
            
        except Exception as e:
            logger.error(f"Error fetching earnings calendar for {ticker}: {e}")
            return []
    
    @staticmethod
    def update_company_earnings(db: Session, company: Company) -> List[EarningsCalendar]:
        """
        Update earnings calendar for a specific company
        FIXED: Changed from async to sync
        """
        try:
            # Fetch latest earnings data (sync call - no await)
            earnings_data = EarningsCalendarService.fetch_earnings_calendar(
                company.ticker,
                start_date=date.today(),
                end_date=date.today() + timedelta(days=90)
            )
            
            updated_earnings = []
            
            for data in earnings_data:
                # Check if entry already exists
                existing = db.query(EarningsCalendar).filter(
                    EarningsCalendar.company_id == company.id,
                    EarningsCalendar.earnings_date == data["earnings_date"]
                ).first()
                
                if existing:
                    # Update existing entry
                    existing.earnings_time = data["earnings_time"]
                    existing.eps_estimate = data["eps_estimate"]
                    existing.revenue_estimate = data["revenue_estimate"]
                    existing.updated_at = datetime.utcnow()
                    existing.source = "fmp"  # Update source
                    updated_earnings.append(existing)
                else:
                    # Create new entry
                    new_earning = EarningsCalendar(
                        company_id=company.id,
                        earnings_date=data["earnings_date"],
                        earnings_time=data["earnings_time"],
                        fiscal_quarter=data["fiscal_quarter"],
                        fiscal_year=data["fiscal_year"],
                        eps_estimate=data["eps_estimate"],
                        revenue_estimate=data["revenue_estimate"],
                        source="fmp"  # Set source to FMP
                    )
                    db.add(new_earning)
                    updated_earnings.append(new_earning)
            
            db.commit()
            
            # Invalidate cache
            cache_key = f"earnings:company:{company.ticker}"
            cache.delete(cache_key)
            
            return updated_earnings
            
        except Exception as e:
            logger.error(f"Error updating earnings for {company.ticker}: {e}")
            db.rollback()
            return []
    
    @staticmethod
    def update_all_sp500_earnings(db: Session) -> int:
        """
        Update earnings calendar for all S&P 500 companies
        FIXED: Removed async - this is now a sync method
        """
        try:
            # Get all S&P 500 companies
            companies = db.query(Company).filter(
                Company.is_sp500 == True,
                Company.is_active == True
            ).all()
            
            # Get all earnings for date range from FMP in one call
            start_date = date.today()
            end_date = start_date + timedelta(days=90)
            
            logger.info(f"Fetching earnings calendar from FMP: {start_date} to {end_date}")
            
            # FIXED: Direct sync call to FMP service (no await)
            all_earnings_data = fmp_service.get_earnings_calendar(
                start_date.isoformat(),
                end_date.isoformat()
            )
            
            if not all_earnings_data:
                logger.warning("No earnings data returned from FMP")
                return 0
            
            logger.info(f"FMP returned {len(all_earnings_data)} total earnings entries")
            
            # Create a map of ticker to earnings data
            earnings_by_ticker = {}
            for item in all_earnings_data:
                ticker = item.get('symbol')
                if ticker:
                    if ticker not in earnings_by_ticker:
                        earnings_by_ticker[ticker] = []
                    earnings_by_ticker[ticker].append(item)
            
            updated_count = 0
            
            for i, company in enumerate(companies):
                if i % 10 == 0:  # Log progress every 10 companies
                    logger.info(f"Updating earnings for companies ({i+1}/{len(companies)})")
                
                ticker_earnings = earnings_by_ticker.get(company.ticker, [])
                
                for item in ticker_earnings:
                    # Parse earnings data
                    earnings_date_str = item.get('date', '')
                    earnings_time_str = item.get('time', 'TNS').upper()
                    
                    # Convert time to enum
                    if earnings_time_str == 'BMO':
                        earnings_time = EarningsTime.BMO
                    elif earnings_time_str == 'AMC':
                        earnings_time = EarningsTime.AMC
                    else:
                        earnings_time = EarningsTime.TNS
                    
                    # Parse date
                    try:
                        earnings_date = datetime.strptime(earnings_date_str, '%Y-%m-%d').date()
                    except:
                        continue
                    
                    # Check if entry exists
                    existing = db.query(EarningsCalendar).filter(
                        EarningsCalendar.company_id == company.id,
                        EarningsCalendar.earnings_date == earnings_date
                    ).first()
                    
                    if existing:
                        # Update existing
                        existing.earnings_time = earnings_time
                        existing.eps_estimate = item.get('epsEstimated')
                        existing.revenue_estimate = item.get('revenueEstimated')
                        existing.updated_at = datetime.utcnow()
                        existing.source = "fmp"
                    else:
                        # Create new
                        new_earning = EarningsCalendar(
                            company_id=company.id,
                            earnings_date=earnings_date,
                            earnings_time=earnings_time,
                            fiscal_quarter=item.get('fiscalDateEnding', ''),
                            fiscal_year=earnings_date.year,
                            eps_estimate=item.get('epsEstimated'),
                            revenue_estimate=item.get('revenueEstimated'),
                            source="fmp"
                        )
                        db.add(new_earning)
                    
                    updated_count += 1
            
            db.commit()
            logger.info(f"Updated {updated_count} earnings entries")
            return updated_count
            
        except Exception as e:
            logger.error(f"Error updating S&P 500 earnings: {e}")
            db.rollback()
            return 0
    
    @staticmethod
    def get_upcoming_earnings(
        db: Session,
        days_ahead: int = 7,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get upcoming earnings announcements
        """
        # Check cache first
        cache_key = f"earnings:upcoming:{days_ahead}:{limit}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        # Calculate date range
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)
        
        # Query upcoming earnings
        earnings = db.query(EarningsCalendar).join(Company).filter(
            EarningsCalendar.earnings_date >= start_date,
            EarningsCalendar.earnings_date <= end_date
        ).order_by(
            EarningsCalendar.earnings_date,
            EarningsCalendar.earnings_time
        ).limit(limit).all()
        
        # Format results
        results = []
        for earning in earnings:
            results.append({
                "id": earning.id,
                "company": {
                    "id": earning.company.id,
                    "ticker": earning.company.ticker,
                    "name": earning.company.name
                },
                "earnings_date": earning.earnings_date.isoformat(),
                "earnings_time": earning.earnings_time.value,
                "fiscal_quarter": earning.fiscal_quarter,
                "eps_estimate": earning.eps_estimate,
                "revenue_estimate": earning.revenue_estimate,
                "is_confirmed": earning.is_confirmed
            })
        
        # Cache results
        cache.set(cache_key, results, ttl=CACHE_TTL["earnings_calendar"])
        
        return results
    
    @staticmethod
    def get_earnings_by_date(
        db: Session,
        target_date: date
    ) -> List[Dict]:
        """
        Get all earnings for a specific date
        """
        # Check cache first
        cache_key = f"earnings:date:{target_date.isoformat()}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        # Query earnings for date
        earnings = db.query(EarningsCalendar).join(Company).filter(
            EarningsCalendar.earnings_date == target_date
        ).order_by(
            EarningsCalendar.earnings_time,
            Company.ticker
        ).all()
        
        # Group by time
        results = {
            "bmo": [],
            "amc": [],
            "tns": []
        }
        
        for earning in earnings:
            earning_data = {
                "id": earning.id,
                "company": {
                    "id": earning.company.id,
                    "ticker": earning.company.ticker,
                    "name": earning.company.name
                },
                "fiscal_quarter": earning.fiscal_quarter,
                "eps_estimate": earning.eps_estimate,
                "revenue_estimate": earning.revenue_estimate,
                "is_confirmed": earning.is_confirmed
            }
            
            results[earning.earnings_time.value].append(earning_data)
        
        # Cache results
        cache.set(cache_key, results, ttl=CACHE_TTL["earnings_calendar"])
        
        return results
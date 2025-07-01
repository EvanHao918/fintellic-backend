# app/services/earnings_calendar_service.py
"""
Service for fetching and managing earnings calendar data
"""
import yfinance as yf
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
import logging

from app.models.company import Company
from app.models.earnings_calendar import EarningsCalendar, EarningsTime
from app.core.cache import cache, CACHE_TTL

logger = logging.getLogger(__name__)


class EarningsCalendarService:
    """Service for managing earnings calendar data"""
    
    @staticmethod
    def fetch_earnings_calendar(
        ticker: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict]:
        """
        Fetch earnings calendar data from yfinance
        """
        try:
            # Default to next 3 months if not specified
            if not start_date:
                start_date = date.today()
            if not end_date:
                end_date = start_date + timedelta(days=90)
            
            # Get ticker data
            stock = yf.Ticker(ticker)
            
            # Get earnings dates
            earnings_dates = stock.earnings_dates
            
            if earnings_dates is None or earnings_dates.empty:
                logger.warning(f"No earnings data found for {ticker}")
                return []
            
            # Filter by date range
            earnings_dates = earnings_dates[
                (earnings_dates.index.date >= start_date) & 
                (earnings_dates.index.date <= end_date)
            ]
            
            # Convert to list of dicts
            results = []
            for idx, row in earnings_dates.iterrows():
                # Determine earnings time based on hour
                hour = idx.hour
                if hour < 9:
                    earnings_time = EarningsTime.BMO
                elif hour >= 16:
                    earnings_time = EarningsTime.AMC
                else:
                    earnings_time = EarningsTime.TNS
                
                results.append({
                    "earnings_date": idx.date(),
                    "earnings_time": earnings_time,
                    "eps_estimate": row.get("EPS Estimate"),
                    "revenue_estimate": row.get("Revenue Estimate"),
                    "fiscal_quarter": f"Q{idx.quarter} {idx.year}",
                    "fiscal_year": idx.year
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Error fetching earnings calendar for {ticker}: {e}")
            return []
    
    @staticmethod
    def update_company_earnings(db: Session, company: Company) -> List[EarningsCalendar]:
        """
        Update earnings calendar for a specific company
        """
        try:
            # Fetch latest earnings data
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
                        source="yfinance"
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
        This should be run as a scheduled task
        """
        try:
            # Get all S&P 500 companies
            companies = db.query(Company).filter(
                Company.is_sp500 == True,
                Company.is_active == True
            ).all()
            
            updated_count = 0
            
            for i, company in enumerate(companies):
                logger.info(f"Updating earnings for {company.ticker} ({i+1}/{len(companies)})")
                
                earnings = EarningsCalendarService.update_company_earnings(db, company)
                if earnings:
                    updated_count += len(earnings)
                
                # Add small delay to avoid rate limiting
                import time
                time.sleep(0.5)
            
            logger.info(f"Updated {updated_count} earnings entries")
            return updated_count
            
        except Exception as e:
            logger.error(f"Error updating S&P 500 earnings: {e}")
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
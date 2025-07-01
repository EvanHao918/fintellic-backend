# app/api/endpoints/earnings.py
"""
Earnings calendar API endpoints
"""
from typing import List, Optional
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.api import deps
from app.models.company import Company
from app.services.earnings_calendar_service import EarningsCalendarService
from app.core.cache import cache

router = APIRouter()


@router.get("/upcoming")
async def get_upcoming_earnings(
    days: int = Query(7, ge=1, le=30, description="Days ahead to look"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Get upcoming earnings announcements
    """
    earnings = EarningsCalendarService.get_upcoming_earnings(db, days, limit)
    
    return {
        "days_ahead": days,
        "count": len(earnings),
        "earnings": earnings
    }


@router.get("/date/{target_date}")
async def get_earnings_by_date(
    target_date: date,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Get all earnings announcements for a specific date
    """
    earnings = EarningsCalendarService.get_earnings_by_date(db, target_date)
    
    # Count total
    total = sum(len(earnings[time]) for time in ["bmo", "amc", "tns"])
    
    return {
        "date": target_date.isoformat(),
        "total": total,
        "earnings": earnings
    }


@router.get("/company/{ticker}")
async def get_company_earnings(
    ticker: str,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Get earnings calendar for a specific company
    """
    # Check cache first
    cache_key = f"earnings:company:{ticker.upper()}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    # Get company
    company = db.query(Company).filter(
        Company.ticker == ticker.upper()
    ).first()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Get earnings from database
    from app.models.earnings_calendar import EarningsCalendar
    earnings = db.query(EarningsCalendar).filter(
        EarningsCalendar.company_id == company.id,
        EarningsCalendar.earnings_date >= date.today()
    ).order_by(EarningsCalendar.earnings_date).all()
    
    result = {
        "company": {
            "id": company.id,
            "ticker": company.ticker,
            "name": company.name
        },
        "earnings": [
            {
                "id": e.id,
                "earnings_date": e.earnings_date.isoformat(),
                "earnings_time": e.earnings_time.value,
                "fiscal_quarter": e.fiscal_quarter,
                "fiscal_year": e.fiscal_year,
                "eps_estimate": e.eps_estimate,
                "revenue_estimate": e.revenue_estimate,
                "is_confirmed": e.is_confirmed,
                "updated_at": e.updated_at.isoformat() if e.updated_at else None
            }
            for e in earnings
        ]
    }
    
    # Cache for 1 hour
    cache.set(cache_key, result, ttl=3600)
    
    return result


@router.post("/update/{ticker}")
async def update_company_earnings(
    ticker: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Update earnings calendar for a specific company
    Requires authentication
    """
    # Get company
    company = db.query(Company).filter(
        Company.ticker == ticker.upper()
    ).first()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Update in background
    def update_task():
        db_new = next(deps.get_db())
        try:
            EarningsCalendarService.update_company_earnings(db_new, company)
        finally:
            db_new.close()
    
    background_tasks.add_task(update_task)
    
    return {
        "message": f"Earnings update started for {ticker}",
        "status": "processing"
    }


@router.get("/calendar/monthly")
async def get_monthly_calendar(
    year: int = Query(..., ge=2020, le=2030),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Get earnings calendar for a specific month
    """
    # Check cache first
    cache_key = f"earnings:calendar:{year}:{month}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    # Calculate date range
    from calendar import monthrange
    start_date = date(year, month, 1)
    _, last_day = monthrange(year, month)
    end_date = date(year, month, last_day)
    
    # Get all earnings for the month
    from app.models.earnings_calendar import EarningsCalendar
    earnings = db.query(EarningsCalendar).join(Company).filter(
        EarningsCalendar.earnings_date >= start_date,
        EarningsCalendar.earnings_date <= end_date
    ).order_by(
        EarningsCalendar.earnings_date,
        EarningsCalendar.earnings_time
    ).all()
    
    # Group by date
    calendar_data = {}
    
    for earning in earnings:
        date_key = earning.earnings_date.isoformat()
        
        if date_key not in calendar_data:
            calendar_data[date_key] = {
                "date": date_key,
                "count": 0,
                "companies": []
            }
        
        calendar_data[date_key]["count"] += 1
        calendar_data[date_key]["companies"].append({
            "ticker": earning.company.ticker,
            "name": earning.company.name,
            "time": earning.earnings_time.value,
            "fiscal_quarter": earning.fiscal_quarter
        })
    
    result = {
        "year": year,
        "month": month,
        "earnings_days": list(calendar_data.values())
    }
    
    # Cache for 1 hour
    cache.set(cache_key, result, ttl=3600)
    
    return result


@router.get("/calendar/weekly")
async def get_weekly_calendar(
    weeks_ahead: int = Query(1, ge=1, le=4),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    """
    Get earnings calendar for the next N weeks
    """
    from datetime import timedelta
    
    # Calculate date range
    start_date = date.today()
    end_date = start_date + timedelta(weeks=weeks_ahead)
    
    # Get earnings
    from app.models.earnings_calendar import EarningsCalendar
    earnings = db.query(EarningsCalendar).join(Company).filter(
        EarningsCalendar.earnings_date >= start_date,
        EarningsCalendar.earnings_date <= end_date
    ).order_by(
        EarningsCalendar.earnings_date,
        EarningsCalendar.earnings_time
    ).all()
    
    # Group by week
    weeks = []
    current_week_start = start_date - timedelta(days=start_date.weekday())
    
    for week_num in range(weeks_ahead):
        week_start = current_week_start + timedelta(weeks=week_num)
        week_end = week_start + timedelta(days=6)
        
        week_earnings = [
            e for e in earnings 
            if week_start <= e.earnings_date <= week_end
        ]
        
        weeks.append({
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "count": len(week_earnings),
            "highlights": [
                {
                    "date": e.earnings_date.isoformat(),
                    "ticker": e.company.ticker,
                    "name": e.company.name,
                    "time": e.earnings_time.value
                }
                for e in week_earnings[:10]  # Top 10 per week
            ]
        })
    
    return {
        "weeks_ahead": weeks_ahead,
        "weeks": weeks
    }
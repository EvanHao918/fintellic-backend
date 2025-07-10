from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.services.view_tracking import ViewTrackingService


router = APIRouter()


@router.get("/users/me/view-stats")
def get_my_view_stats(
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get current user's viewing statistics
    """
    stats = ViewTrackingService.get_user_view_stats(db, current_user.id)
    return stats


@router.get("/filings/check-access/{filing_id}")
def check_can_view_filing(
    filing_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(deps.get_db)
):
    """
    Check if current user can view a specific filing
    """
    result = ViewTrackingService.can_view_filing(db, current_user, filing_id)
    return result
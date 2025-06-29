from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.user import User, UserTier
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash, verify_password


class CRUDUser:
    """CRUD operations for User model"""
    
    def get(self, db: Session, id: int) -> Optional[User]:
        """Get user by ID"""
        return db.query(User).filter(User.id == id).first()
    
    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        """Get user by email"""
        return db.query(User).filter(User.email == email).first()
    
    def get_by_username(self, db: Session, username: str) -> Optional[User]:
        """Get user by username"""
        return db.query(User).filter(User.username == username).first()
    
    def get_by_email_or_username(self, db: Session, email_or_username: str) -> Optional[User]:
        """Get user by email or username"""
        return db.query(User).filter(
            or_(
                User.email == email_or_username,
                User.username == email_or_username
            )
        ).first()
    
    def get_multi(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> List[User]:
        """Get multiple users"""
        return db.query(User).offset(skip).limit(limit).all()
    
    def create(self, db: Session, *, obj_in: UserCreate) -> User:
        """Create new user"""
        db_obj = User(
            email=obj_in.email,
            hashed_password=get_password_hash(obj_in.password),
            full_name=obj_in.full_name,
            username=obj_in.username,
            is_active=obj_in.is_active,
            tier=UserTier.FREE,
            daily_reports_count=0,
            daily_reports_reset_at=datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(
        self, db: Session, *, db_obj: User, obj_in: UserUpdate
    ) -> User:
        """Update user"""
        update_data = obj_in.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db_obj.updated_at = datetime.utcnow()
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update_last_login(self, db: Session, *, user: User) -> User:
        """Update user's last login timestamp"""
        user.last_login_at = datetime.utcnow()
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    
    def authenticate(self, db: Session, *, email: str, password: str) -> Optional[User]:
        """Authenticate user by email and password"""
        user = self.get_by_email(db, email=email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
    
    def is_active(self, user: User) -> bool:
        """Check if user is active"""
        return user.is_active
    
    def is_pro(self, user: User) -> bool:
        """Check if user has pro subscription"""
        if user.tier != UserTier.PRO:
            return False
        if user.subscription_expires_at:
            return user.subscription_expires_at > datetime.utcnow()
        return True
    
    def increment_daily_reports(self, db: Session, *, user: User) -> User:
        """Increment daily reports count for free users"""
        if user.tier == UserTier.FREE:
            user.daily_reports_count += 1
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    
    def upgrade_to_pro(
        self, db: Session, *, user: User, expires_at: datetime
    ) -> User:
        """Upgrade user to pro tier"""
        user.tier = UserTier.PRO
        user.subscription_expires_at = expires_at
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


# Create single instance
crud_user = CRUDUser()
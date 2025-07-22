from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import NullPool
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,  # Disable connection pooling for development
    echo=False,  # Set to True to see SQL queries in console
)

# Create session factory
session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 原始的 SessionLocal 保持不变（向后兼容）
SessionLocal = session_factory

# 新增：线程安全的 session（供 Celery 使用）
ThreadSafeSession = scoped_session(session_factory)


def get_db() -> Session:
    """
    Dependency to get database session.
    Usage:
        @app.get("/items/")
        def read_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


# 新增：用于 Celery 任务的上下文管理器
from contextlib import contextmanager

@contextmanager
def get_task_db():
    """Get a thread-safe database session for Celery tasks"""
    session = ThreadSafeSession()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        ThreadSafeSession.remove()  # 重要：清理线程本地会话
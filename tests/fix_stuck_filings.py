#!/usr/bin/env python
"""
修复卡在 ai_processing 状态的财报
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.filing import Filing, ProcessingStatus
from app.models.company import Company
from app.tasks.filing_tasks import process_filing_task
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建数据库连接
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def fix_stuck_filings():
    """修复卡住的财报"""
    db = SessionLocal()
    
    try:
        # 1. 先处理有AI内容的财报
        filings_with_ai = db.query(Filing).filter(
            Filing.status == ProcessingStatus.AI_PROCESSING,
            Filing.ai_summary.isnot(None)
        ).all()
        
        completed_count = 0
        for filing in filings_with_ai:
            if filing.ai_summary and len(filing.ai_summary) > 50:
                logger.info(f"Filing {filing.id} has AI content ({len(filing.ai_summary)} chars), marking as COMPLETED")
                filing.status = ProcessingStatus.COMPLETED
                filing.processing_completed_at = datetime.now(timezone.utc)
                filing.error_message = None
                completed_count += 1
        
        db.commit()
        logger.info(f"✅ Marked {completed_count} filings with AI content as COMPLETED")
        
        # 2. 重置其他卡住的财报
        stuck_filings = db.query(Filing, Company).join(
            Company, Filing.company_id == Company.id
        ).filter(
            Filing.status == ProcessingStatus.AI_PROCESSING
        ).all()
        
        reset_count = 0
        requeue_count = 0
        
        print(f"\n将重置 {len(stuck_filings)} 个卡住的财报:")
        print("="*60)
        
        for filing, company in stuck_filings:
            # 计算运行时间
            if filing.processing_started_at:
                now = datetime.now(timezone.utc)
                start_time = filing.processing_started_at
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
                duration = now - start_time
                duration_mins = duration.total_seconds() / 60
            else:
                duration_mins = 0
            
            # 如果运行超过30分钟，认为是真的卡住了
            if duration_mins > 30:
                print(f"Resetting: {company.ticker} {filing.filing_type.value} (ID: {filing.id}) - ran for {duration_mins:.1f} mins")
                
                # 重置状态
                filing.status = ProcessingStatus.PENDING
                filing.processing_started_at = None
                filing.processing_completed_at = None
                filing.error_message = None
                reset_count += 1
                
                # 提交更改
                db.commit()
                
                # 重新加入队列
                try:
                    task = process_filing_task.delay(filing.id)
                    logger.info(f"Requeued filing {filing.id} with task ID: {task.id}")
                    requeue_count += 1
                except Exception as e:
                    logger.error(f"Failed to requeue filing {filing.id}: {e}")
        
        print("="*60)
        print(f"\n✅ 修复完成:")
        print(f"  - 标记为完成: {completed_count} 个")
        print(f"  - 重置状态: {reset_count} 个")
        print(f"  - 重新加入队列: {requeue_count} 个")
        
        # 3. 显示当前系统状态
        print("\n当前系统状态:")
        status_counts = db.query(
            Filing.status, 
            db.func.count(Filing.id)
        ).group_by(Filing.status).all()
        
        for status, count in status_counts:
            print(f"  - {status.value}: {count}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    # 确认操作
    print("⚠️  警告: 这将重置所有卡住的财报并重新处理它们")
    response = input("是否继续? (y/n): ")
    
    if response.lower() == 'y':
        fix_stuck_filings()
    else:
        print("操作已取消")
#!/usr/bin/env python3
"""
重新处理失败的财报
使用改进的下载器重新下载和处理之前失败的财报
"""

import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
from app.tasks.filing_tasks import process_filing_task
import logging

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_failed_filings(db: Session):
    """获取所有失败的财报"""
    return db.query(Filing).filter(
        Filing.status.in_([ProcessingStatus.FAILED, ProcessingStatus.PENDING])
    ).all()


def get_incomplete_filings(db: Session):
    """获取内容不完整的财报（如只有73字符的）"""
    return db.query(Filing).filter(
        Filing.status == ProcessingStatus.COMPLETED,
        Filing.ai_summary.isnot(None),
        Filing.ai_summary != ""
    ).all()


async def reprocess_filing(filing_id: int):
    """重新处理单个财报"""
    try:
        logger.info(f"Reprocessing filing ID: {filing_id}")
        # 调用Celery任务（同步方式）
        process_filing_task.delay(filing_id)
        return True
    except Exception as e:
        logger.error(f"Error reprocessing filing {filing_id}: {e}")
        return False


async def main():
    """主函数"""
    db = SessionLocal()
    
    try:
        # 1. 获取失败的财报
        failed_filings = get_failed_filings(db)
        logger.info(f"Found {len(failed_filings)} failed/pending filings")
        
        # 2. 获取内容不完整的财报
        incomplete_filings = get_incomplete_filings(db)
        
        # 检查哪些内容太短
        short_content_filings = []
        for filing in incomplete_filings:
            if filing.ai_summary and len(filing.ai_summary) < 100:
                short_content_filings.append(filing)
        
        logger.info(f"Found {len(short_content_filings)} filings with short content")
        
        # 3. 合并需要重新处理的财报
        all_filings_to_reprocess = failed_filings + short_content_filings
        logger.info(f"Total filings to reprocess: {len(all_filings_to_reprocess)}")
        
        if not all_filings_to_reprocess:
            logger.info("No filings need reprocessing!")
            return
        
        # 4. 显示将要处理的财报
        print("\n将要重新处理以下财报：")
        print("-" * 80)
        print(f"{'Company':<10} {'Type':<8} {'Date':<12} {'Status':<15} {'Current Issue':<30}")
        print("-" * 80)
        
        for filing in all_filings_to_reprocess[:20]:  # 显示前20个
            issue = "Failed" if filing.status == ProcessingStatus.FAILED else \
                    f"Short content ({len(filing.ai_summary or '')} chars)"
            print(f"{filing.company.ticker:<10} {filing.filing_type.value:<8} "
                  f"{filing.filing_date.strftime('%Y-%m-%d'):<12} "
                  f"{filing.status.value:<15} {issue:<30}")
        
        if len(all_filings_to_reprocess) > 20:
            print(f"... and {len(all_filings_to_reprocess) - 20} more")
        
        print("-" * 80)
        
        # 5. 确认是否继续
        response = input(f"\n是否重新处理这 {len(all_filings_to_reprocess)} 个财报? (y/n): ")
        if response.lower() != 'y':
            logger.info("用户取消操作")
            return
        
        # 6. 重置状态并重新处理
        logger.info("开始重新处理...")
        
        for i, filing in enumerate(all_filings_to_reprocess, 1):
            # 重置状态为PENDING
            filing.status = ProcessingStatus.PENDING
            filing.error_message = None
            filing.processing_started_at = None
            filing.processing_completed_at = None
            db.commit()
            
            # 重新处理
            await reprocess_filing(filing.id)
            
            logger.info(f"[{i}/{len(all_filings_to_reprocess)}] "
                       f"Queued {filing.company.ticker} {filing.filing_type.value} for reprocessing")
            
            # 每10个暂停一下，避免过载
            if i % 10 == 0:
                await asyncio.sleep(2)
        
        logger.info("✅ 所有财报已加入处理队列")
        print("\n" + "="*60)
        print("✅ 重新处理已启动！")
        print("="*60)
        print("\n监控进度的方法：")
        print("1. 查看日志: tail -f logs/celery.log")
        print("2. 查看数据库状态: python scripts/check_filing_status.py")
        print("3. 查看实时处理: python monitor_system.py")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
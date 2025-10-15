# scripts/reset_stuck_filings.py
"""
重置卡住的AI处理任务
"""
import sys
import argparse
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
import pytz

def reset_stuck_filings(hours: int = 6, dry_run: bool = False):
    """重置卡住超过指定小时数的财报"""
    db = SessionLocal()
    
    try:
        # 计算时间阈值
        now = datetime.utcnow()
        if now.tzinfo is None:
            now = now.replace(tzinfo=pytz.UTC)
        threshold = now - timedelta(hours=hours)
        
        # 查找卡住的财报
        stuck_filings = db.query(Filing).filter(
            Filing.status == ProcessingStatus.AI_PROCESSING,
            Filing.processing_started_at < threshold
        ).all()
        
        print(f"\n🔍 找到 {len(stuck_filings)} 个卡住超过 {hours} 小时的财报")
        
        if not stuck_filings:
            print("✅ 没有需要重置的财报")
            return
        
        # 显示将要重置的财报
        print("\n将要重置的财报:")
        print("-" * 60)
        print(f"{'ID':<6} {'Ticker':<8} {'Type':<8} {'Started At':<20}")
        print("-" * 60)
        
        for filing in stuck_filings[:20]:  # 只显示前20个
            print(f"{filing.id:<6} {filing.company.ticker:<8} {filing.filing_type.value:<8} "
                  f"{str(filing.processing_started_at)[:19]}")
        
        if len(stuck_filings) > 20:
            print(f"... 还有 {len(stuck_filings) - 20} 个")
        
        if dry_run:
            print("\n🔸 DRY RUN 模式 - 不会实际修改数据")
            return
        
        # 确认
        confirm = input(f"\n确定要重置这 {len(stuck_filings)} 个财报吗? (yes/no): ")
        if confirm.lower() != 'yes':
            print("❌ 取消操作")
            return
        
        # 重置状态
        count = 0
        for filing in stuck_filings:
            filing.status = ProcessingStatus.DOWNLOADED
            filing.processing_started_at = None
            filing.error_message = f"Reset from stuck ai_processing at {datetime.utcnow()}"
            count += 1
        
        db.commit()
        print(f"\n✅ 成功重置 {count} 个财报状态为 DOWNLOADED")
        print("这些财报将被重新加入处理队列")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='重置卡住的AI处理任务')
    parser.add_argument('--hours', type=int, default=6, 
                        help='重置卡住超过多少小时的任务 (默认: 6)')
    parser.add_argument('--dry-run', action='store_true',
                        help='只显示将要重置的任务，不实际执行')
    
    args = parser.parse_args()
    reset_stuck_filings(args.hours, args.dry_run)
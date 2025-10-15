# scripts/trigger_single_filing.py
"""
手动触发单个财报的处理
"""
import sys
import asyncio
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
from app.tasks.filing_tasks import process_filing_task

def trigger_filing(filing_id: int):
    """手动触发一个财报的处理"""
    db = SessionLocal()
    
    try:
        filing = db.query(Filing).filter(Filing.id == filing_id).first()
        if not filing:
            print(f"❌ 找不到ID为 {filing_id} 的财报")
            return
        
        print(f"\n📄 财报信息:")
        print(f"  ID: {filing.id}")
        print(f"  公司: {filing.company.ticker}")
        print(f"  类型: {filing.filing_type.value}")
        print(f"  状态: {filing.status.value}")
        print(f"  处理开始时间: {filing.processing_started_at}")
        
        if filing.status != ProcessingStatus.AI_PROCESSING:
            confirm = input(f"\n⚠️  财报状态是 {filing.status.value}，确定要处理吗? (yes/no): ")
            if confirm.lower() != 'yes':
                print("❌ 取消操作")
                return
        
        print("\n🚀 触发处理任务...")
        
        # 直接调用任务（同步方式，便于调试）
        try:
            result = process_filing_task(filing.id)
            print(f"✅ 任务完成: {result}")
        except Exception as e:
            print(f"❌ 任务失败: {e}")
            import traceback
            traceback.print_exc()
            
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        # 默认处理最早的一个卡住的财报
        db = SessionLocal()
        stuck_filing = db.query(Filing).filter(
            Filing.status == ProcessingStatus.AI_PROCESSING
        ).order_by(Filing.processing_started_at).first()
        
        if stuck_filing:
            filing_id = stuck_filing.id
            print(f"使用最早卡住的财报 ID: {filing_id}")
        else:
            print("用法: python trigger_single_filing.py <filing_id>")
            sys.exit(1)
        db.close()
    else:
        filing_id = int(sys.argv[1])
    
    trigger_filing(filing_id)
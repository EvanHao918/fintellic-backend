#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from app.core.database import SessionLocal
from app.models import Filing, ProcessingStatus
from sqlalchemy import desc, func
from datetime import datetime, timedelta

print("=== STEP 5: 检查财报处理状态 ===\n")

db = SessionLocal()

try:
    # 1. 按状态统计
    status_counts = db.query(
        Filing.status, 
        func.count(Filing.id)
    ).group_by(Filing.status).all()
    
    print("财报处理状态统计:")
    for status, count in status_counts:
        print(f"- {status.value}: {count} 个")
    
    # 2. 检查今天的财报
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_filings = db.query(Filing).filter(
        Filing.created_at >= today_start
    ).all()
    
    print(f"\n今天新增的财报: {len(today_filings)} 个")
    
    # 3. 检查待处理的财报
    pending = db.query(Filing).filter(
        Filing.status == ProcessingStatus.PENDING
    ).count()
    
    if pending > 0:
        print(f"\n⏳ 有 {pending} 个财报待处理")
        
        # 显示前5个待处理
        pending_filings = db.query(Filing).filter(
            Filing.status == ProcessingStatus.PENDING
        ).limit(5).all()
        
        print("\n待处理的财报:")
        for f in pending_filings:
            print(f"- {f.company.ticker}: {f.filing_type.value} (创建于 {f.created_at})")
    
    # 4. 检查已完成的财报
    completed = db.query(Filing).filter(
        Filing.status == ProcessingStatus.COMPLETED
    ).order_by(desc(Filing.updated_at)).limit(5).all()
    
    if completed:
        print("\n最近完成处理的财报:")
        for f in completed:
            print(f"- {f.company.ticker}: {f.filing_type.value}")
            if f.ai_summary:
                print(f"  ✅ AI摘要: {f.ai_summary[:100]}...")
            if f.sentiment_score is not None:
                print(f"  ✅ 情绪分数: {f.sentiment_score}")
    
except Exception as e:
    print(f"错误: {e}")
finally:
    db.close()

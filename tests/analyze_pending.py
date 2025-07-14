#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from app.core.database import SessionLocal
from app.models import Filing, ProcessingStatus
from datetime import datetime, timedelta
from sqlalchemy import func

print("=== 分析待处理财报 ===\n")

db = SessionLocal()

try:
    # 1. 按创建时间分组
    print("1. 待处理财报的时间分布:")
    pending_filings = db.query(Filing).filter(
        Filing.status == ProcessingStatus.PENDING
    ).order_by(Filing.created_at).all()
    
    # 按天分组
    date_groups = {}
    for f in pending_filings:
        date_key = f.created_at.date()
        if date_key not in date_groups:
            date_groups[date_key] = []
        date_groups[date_key].append(f)
    
    for date, filings in sorted(date_groups.items()):
        age_days = (datetime.now().date() - date).days
        print(f"\n{date} ({age_days}天前): {len(filings)}个")
        for f in filings[:3]:  # 显示前3个
            print(f"  - {f.company.ticker}: {f.filing_type.value} (ID: {f.id})")
        if len(filings) > 3:
            print(f"  ... 还有 {len(filings)-3} 个")
    
    # 2. 分析为什么没有被处理
    print("\n\n2. 待处理财报详情:")
    
    # 最老的5个
    oldest_pending = db.query(Filing).filter(
        Filing.status == ProcessingStatus.PENDING
    ).order_by(Filing.created_at).limit(5).all()
    
    print("\n最老的待处理财报:")
    for f in oldest_pending:
        age = (datetime.now() - f.created_at.replace(tzinfo=None)).days
        print(f"\n{f.company.ticker} - {f.filing_type.value}")
        print(f"  ID: {f.id}")
        print(f"  创建时间: {f.created_at} ({age}天前)")
        print(f"  Accession: {f.accession_number}")
        
        # 检查是否是测试数据
        if f.accession_number.startswith("TEST"):
            print(f"  ⚠️ 这是测试数据")
        elif age > 30:
            print(f"  ⚠️ 超过30天的老数据，可能已不在SEC网站上")
    
    # 3. 检查 Celery 任务历史
    print("\n\n3. 任务处理情况:")
    
    # 今天处理的任务
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_processed = db.query(Filing).filter(
        Filing.updated_at >= today,
        Filing.status != ProcessingStatus.PENDING
    ).count()
    
    print(f"今天处理的任务数: {today_processed}")
    
    # 4. 建议
    print("\n\n4. 分析结果:")
    
    recent_pending = sum(1 for f in pending_filings if (datetime.now() - f.created_at.replace(tzinfo=None)).days < 7)
    old_pending = len(pending_filings) - recent_pending
    
    print(f"- 最近7天的待处理: {recent_pending}个")
    print(f"- 超过7天的待处理: {old_pending}个")
    
    if old_pending > 0:
        print(f"\n⚠️ 有 {old_pending} 个老的待处理任务，建议清理或标记为失败")
    
    # 5. 检查是否有重复
    print("\n\n5. 检查重复:")
    duplicates = db.query(
        Filing.company_id,
        Filing.filing_type,
        Filing.filing_date,
        func.count(Filing.id).label('count')
    ).filter(
        Filing.status == ProcessingStatus.PENDING
    ).group_by(
        Filing.company_id,
        Filing.filing_type,
        Filing.filing_date
    ).having(func.count(Filing.id) > 1).all()
    
    if duplicates:
        print(f"发现 {len(duplicates)} 组重复的待处理财报")
        for d in duplicates:
            print(f"  - 公司ID {d[0]}, 类型 {d[1]}, 数量 {d[3]}")
    else:
        print("没有发现重复的待处理财报")
        
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()

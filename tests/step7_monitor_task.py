#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import time
from app.core.database import SessionLocal
from app.models import Filing, ProcessingStatus
from app.core.celery_app import celery_app

print("=== STEP 7: 监控任务执行状态 ===\n")

# 任务 ID（从上一步获得）
task_id = "43f91897-c79d-4abf-aee8-e55d17f494bf"
filing_id = 4

print(f"监控任务 ID: {task_id}")
print(f"财报 ID: {filing_id}\n")

# 检查任务状态
result = celery_app.AsyncResult(task_id)
print(f"任务状态: {result.state}")
print(f"任务信息: {result.info}\n")

# 检查财报状态
db = SessionLocal()
try:
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if filing:
        print(f"财报状态: {filing.status.value}")
        print(f"公司: {filing.company.ticker} - {filing.company.name}")
        print(f"财报类型: {filing.filing_type.value}")
        print(f"创建时间: {filing.created_at}")
        print(f"更新时间: {filing.updated_at}")
        
        if filing.status == ProcessingStatus.COMPLETED:
            print("\n✅ 处理完成!")
            if filing.ai_summary:
                print(f"AI 摘要: {filing.ai_summary[:200]}...")
        elif filing.status == ProcessingStatus.FAILED:
            print("\n❌ 处理失败!")
            if filing.error_message:
                print(f"错误信息: {filing.error_message}")
                
    # 检查所有待处理任务
    print("\n\n当前任务队列状态:")
    pending_count = db.query(Filing).filter(
        Filing.status == ProcessingStatus.PENDING
    ).count()
    processing_count = db.query(Filing).filter(
        Filing.status == ProcessingStatus.PROCESSING  
    ).count()
    
    print(f"待处理: {pending_count}")
    print(f"处理中: {processing_count}")
    
except Exception as e:
    print(f"错误: {e}")
finally:
    db.close()

# 显示最近的错误（如果有）
print("\n\n检查最近的失败任务:")
db = SessionLocal()
try:
    failed_filings = db.query(Filing).filter(
        Filing.status == ProcessingStatus.FAILED
    ).limit(5).all()
    
    if failed_filings:
        for f in failed_filings:
            print(f"\n❌ {f.company.ticker} - {f.filing_type.value}")
            if f.error_message:
                print(f"   错误: {f.error_message[:100]}...")
    else:
        print("没有失败的任务")
        
except Exception as e:
    print(f"错误: {e}")
finally:
    db.close()

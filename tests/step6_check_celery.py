#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models import Filing, ProcessingStatus
import redis
import json

print("=== STEP 6: 检查 Celery 任务队列状态 ===\n")

# 1. 检查 Redis 连接
try:
    r = redis.Redis(host='localhost', port=6379, db=0)
    r.ping()
    print("✅ Redis 连接正常")
    
    # 检查队列中的任务数
    celery_queue_length = r.llen('celery')
    print(f"Celery 队列中的任务数: {celery_queue_length}")
    
except Exception as e:
    print(f"❌ Redis 连接失败: {e}")

# 2. 检查 Celery 是否正在运行
print("\n检查 Celery worker 状态:")
try:
    # 获取活跃的 worker
    inspect = celery_app.control.inspect()
    active_workers = inspect.active()
    
    if active_workers:
        print(f"✅ 找到 {len(active_workers)} 个活跃的 worker")
        for worker, tasks in active_workers.items():
            print(f"  - {worker}: {len(tasks)} 个活跃任务")
    else:
        print("❌ 没有找到活跃的 Celery worker!")
        print("请确保 Celery worker 正在运行")
        
except Exception as e:
    print(f"❌ 无法检查 Celery 状态: {e}")

# 3. 手动触发一个待处理财报的处理
print("\n尝试手动触发待处理财报的处理...")
db = SessionLocal()
try:
    # 获取一个待处理的财报
    pending_filing = db.query(Filing).filter(
        Filing.status == ProcessingStatus.PENDING
    ).first()
    
    if pending_filing:
        print(f"找到待处理财报: {pending_filing.company.ticker} - {pending_filing.filing_type.value}")
        
        # 检查是否可以导入任务
        try:
            from app.tasks.filing_tasks import process_filing_task
            print("✅ 成功导入 filing_tasks")
            
            # 发送任务到队列
            print(f"发送处理任务到队列: Filing ID {pending_filing.id}")
            result = process_filing_task.delay(pending_filing.id)
            print(f"任务 ID: {result.id}")
            
        except ImportError as e:
            print(f"❌ 无法导入任务: {e}")
            
except Exception as e:
    print(f"错误: {e}")
finally:
    db.close()

# 4. 检查 Celery 日志提示
print("\n\n💡 建议检查:")
print("1. 查看 Celery 日志: tail -f logs/celery.log")
print("2. 确保 Celery worker 正在运行: ps aux | grep celery")
print("3. 重启 Celery: ./scripts/stop_fintellic.sh && ./scripts/start_fintellic.sh")

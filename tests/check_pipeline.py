#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from app.core.database import SessionLocal
from app.models import Filing, ProcessingStatus
from datetime import datetime, timedelta
import redis

print("=== 检查任务链各环节 ===\n")

db = SessionLocal()
r = redis.Redis(host='localhost', port=6379, db=0)

# 1. 扫描器
recent = db.query(Filing).filter(
    Filing.created_at >= datetime.now() - timedelta(hours=1)
).count()
print(f"1. 扫描器: {'✅ 工作中' if recent > 0 else '⚠️  最近1小时无新财报'} ({recent}个)")

# 2. 数据库记录
total = db.query(Filing).count()
print(f"2. 数据库: ✅ {total} 条记录")

# 3. 下载状态
downloaded = Path("data/filings").glob("*/*/*")
download_count = len(list(downloaded))
print(f"3. 下载器: ✅ {download_count} 个文件")

# 4. AI处理
completed = db.query(Filing).filter(
    Filing.status == ProcessingStatus.COMPLETED,
    Filing.ai_summary != None
).count()
print(f"4. AI处理: {'✅' if completed > 0 else '❌'} {completed} 个完成")

# 5. 缓存
cache_keys = r.dbsize()
print(f"5. 缓存层: ✅ {cache_keys} 个缓存键")

# 6. API
import requests
try:
    resp = requests.get("http://localhost:8000/health")
    print(f"6. API: {'✅ 在线' if resp.status_code == 200 else '❌ 离线'}")
except:
    print("6. API: ❌ 离线")

db.close()

print("\n📌 注意事项:")
print("- AI处理需要有效的 OpenAI API Key")
print("- 前端推送需要实现 WebSocket（当前可能未实现）")
print("- 移动端通过轮询 API 获取更新")

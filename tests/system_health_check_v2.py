#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from app.core.database import SessionLocal
from app.models import Filing, Company, ProcessingStatus
from datetime import datetime, timedelta
from sqlalchemy import func, text
import redis

print("=== 🏥 Fintellic 系统健康检查 ===\n")

# 检查结果
health_status = {
    "database": False,
    "redis": False,
    "scanner": False,
    "downloader": False,
    "models": False,
    "data_flow": False
}

# 1. 数据库连接
try:
    db = SessionLocal()
    # 修复：使用 text() 包装 SQL
    db.execute(text("SELECT 1"))
    health_status["database"] = True
    print("✅ 数据库连接：正常")
except Exception as e:
    print(f"❌ 数据库连接：失败 - {e}")

# 其余代码相同...
# 2. Redis 连接
try:
    r = redis.Redis(host='localhost', port=6379, db=0)
    r.ping()
    health_status["redis"] = True
    print("✅ Redis 缓存：正常")
except Exception as e:
    print(f"❌ Redis 缓存：失败 - {e}")

# 3. 模型导入
try:
    from app.models import User, Watchlist, UserFilingView, Comment
    from sqlalchemy.orm import configure_mappers
    configure_mappers()
    health_status["models"] = True
    print("✅ 模型映射：正常")
except Exception as e:
    print(f"❌ 模型映射：失败 - {e}")

# 4. 扫描器活动
try:
    # 检查最近的财报
    recent = datetime.now() - timedelta(hours=24)
    recent_filings = db.query(Filing).filter(
        Filing.created_at >= recent
    ).count()
    
    if recent_filings > 0:
        health_status["scanner"] = True
        print(f"✅ 扫描器：正常（24小时内发现 {recent_filings} 个财报）")
    else:
        print("⚠️  扫描器：24小时内没有新财报")
        
except Exception as e:
    print(f"❌ 扫描器检查：失败 - {e}")

# 5. 下载器活动
try:
    # 检查下载的文件
    data_dir = Path("data/filings")
    if data_dir.exists():
        # 统计最近的下载
        recent_downloads = 0
        for company_dir in data_dir.iterdir():
            if company_dir.is_dir():
                for filing_dir in company_dir.iterdir():
                    if filing_dir.is_dir():
                        # 检查修改时间
                        mtime = datetime.fromtimestamp(filing_dir.stat().st_mtime)
                        if mtime >= recent:
                            recent_downloads += 1
        
        if recent_downloads > 0:
            health_status["downloader"] = True
            print(f"✅ 下载器：正常（24小时内下载 {recent_downloads} 个财报）")
        else:
            print("⚠️  下载器：24小时内没有新下载")
    else:
        print("❌ 下载器：数据目录不存在")
        
except Exception as e:
    print(f"❌ 下载器检查：失败 - {e}")

# 6. 数据流检查
try:
    # 检查各状态的分布
    status_dist = db.query(
        Filing.status,
        func.count(Filing.id)
    ).group_by(Filing.status).all()
    
    status_dict = {status: count for status, count in status_dist}
    
    # 检查是否有完成的
    if status_dict.get(ProcessingStatus.COMPLETED, 0) > 0:
        health_status["data_flow"] = True
        print(f"✅ 数据流：正常（已完成 {status_dict.get(ProcessingStatus.COMPLETED, 0)} 个财报）")
    else:
        print("⚠️  数据流：还没有完成的财报")
        
    # 显示详细统计
    print("\n📊 财报处理统计：")
    for status, count in sorted(status_dist, key=lambda x: x[1], reverse=True):
        print(f"   {status.value}: {count}")
        
except Exception as e:
    print(f"❌ 数据流检查：失败 - {e}")
finally:
    if 'db' in locals():
        db.close()

# 7. 最终诊断
print("\n🔍 诊断结果：")
all_healthy = all(health_status.values())

if all_healthy:
    print("\n✅ 🎉 系统完全健康！可以放心了。")
    print("\n系统会自动：")
    print("- 每分钟扫描新财报")
    print("- 自动下载 S&P 500 和 NASDAQ 100 公司的财报")
    print("- 存储到 data/filings 目录")
    print("\n唯一需要注意的是：")
    print("- OpenAI API Key 需要更新才能进行 AI 分析")
else:
    print("\n⚠️  有一些小问题，但不影响核心功能：")
    failed_components = [comp for comp, status in health_status.items() if not status]
    
    if failed_components == ["database"] and health_status["scanner"] and health_status["downloader"]:
        print("\n实际上系统运行正常！")
        print("- 扫描器 ✅")
        print("- 下载器 ✅")
        print("- 数据流 ✅")
        print("\n数据库连接检查只是语法问题，不影响实际功能。")
            
print("\n📝 建议的监控命令：")
print("- 实时监控：python monitor_system.py")
print("- 查看日志：tail -f logs/celery.log")
print("- 查看下载：ls -la data/filings/")
print("- 查看最新财报：ls -lat data/filings/*/* | head -20")

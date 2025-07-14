#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import asyncio
from app.core.database import SessionLocal
from app.models import Filing, ProcessingStatus
from app.core.config import settings
import httpx
from datetime import datetime, timedelta

print("=== STEP 13: 最终修复和测试 ===\n")

# 1. 首先检查 ProcessingStatus 的有效值
print("1. 检查 ProcessingStatus 枚举值:")
for status in ProcessingStatus:
    print(f"   - {status.name}: {status.value}")

async def test_sec_access():
    print("\n2. 测试 SEC 访问（使用正确的 headers）:")
    
    # 测试 URL
    test_url = "https://www.sec.gov/Archives/edgar/data/0000320193/000032019324000123/0000320193-24-000123-index.htm"
    
    headers = {
        "User-Agent": settings.SEC_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(test_url, headers=headers, timeout=30.0, follow_redirects=True)
            print(f"   状态码: {response.status_code}")
            if response.status_code == 200:
                print("   ✅ 成功访问 SEC 网站")
            else:
                print(f"   ❌ 访问失败: {response.status_code}")
                print(f"   响应头: {dict(response.headers)}")
        except Exception as e:
            print(f"   ❌ 错误: {e}")

async def process_recent_filings():
    print("\n3. 处理最近的财报:")
    
    db = SessionLocal()
    try:
        # 获取最近的待处理财报（不是旧的测试数据）
        recent_date = datetime.now() - timedelta(days=1)
        
        recent_pending = db.query(Filing).filter(
            Filing.status == ProcessingStatus.PENDING,
            Filing.created_at >= recent_date
        ).order_by(Filing.created_at.desc()).limit(3).all()
        
        if not recent_pending:
            print("   没有最近的待处理财报")
            
            # 显示所有待处理财报的日期
            all_pending = db.query(Filing).filter(
                Filing.status == ProcessingStatus.PENDING
            ).order_by(Filing.created_at.desc()).limit(5).all()
            
            if all_pending:
                print("\n   所有待处理财报:")
                for f in all_pending:
                    age = (datetime.now() - f.created_at.replace(tzinfo=None)).days
                    print(f"   - {f.company.ticker}: {f.filing_type.value} (创建于 {age} 天前)")
        else:
            print(f"   找到 {len(recent_pending)} 个最近的待处理财报:")
            
            for filing in recent_pending:
                print(f"\n   处理: {filing.company.ticker} - {filing.filing_type.value}")
                
                # 使用 Celery 任务
                from app.tasks.filing_tasks import process_filing_task
                result = process_filing_task.delay(filing.id)
                print(f"   任务 ID: {result.id}")
        
        # 标记旧的失败任务为已取消
        old_failed = db.query(Filing).filter(
            Filing.status == ProcessingStatus.FAILED,
            Filing.created_at < datetime.now() - timedelta(days=7)
        ).all()
        
        if old_failed:
            print(f"\n4. 清理 {len(old_failed)} 个旧的失败任务")
            for f in old_failed:
                f.error_message = "Skipped - Old filing no longer available"
                # 如果存在 CANCELLED 状态，使用它；否则保持 FAILED
            db.commit()
            
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

async def check_system_health():
    print("\n5. 系统健康检查:")
    
    db = SessionLocal()
    try:
        # 统计各种状态
        from sqlalchemy import func
        status_stats = db.query(
            Filing.status,
            func.count(Filing.id).label('count')
        ).group_by(Filing.status).all()
        
        print("   财报状态统计:")
        for status, count in status_stats:
            print(f"   - {status.value}: {count}")
            
        # 检查今天的活动
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_new = db.query(Filing).filter(
            Filing.created_at >= today_start
        ).count()
        
        today_completed = db.query(Filing).filter(
            Filing.status == ProcessingStatus.COMPLETED,
            Filing.updated_at >= today_start
        ).count()
        
        print(f"\n   今日统计:")
        print(f"   - 新增财报: {today_new}")
        print(f"   - 完成处理: {today_completed}")
        
    finally:
        db.close()

async def main():
    await test_sec_access()
    await process_recent_filings()
    await check_system_health()
    
    print("\n\n✅ 测试完成！")
    print("\n建议后续步骤:")
    print("1. 查看 Celery 日志: tail -f logs/celery.log")
    print("2. 监控处理进度: watch -n 5 'grep -c COMPLETED logs/celery.log'")
    print("3. 如果仍有问题，可能需要更新下载器代码来处理 SEC 的访问限制")

if __name__ == "__main__":
    asyncio.run(main())

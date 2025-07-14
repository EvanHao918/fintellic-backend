#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import time
from app.core.database import SessionLocal
from app.models import Filing, ProcessingStatus
from datetime import datetime, timedelta
from sqlalchemy import func, desc

def monitor():
    while True:
        db = SessionLocal()
        try:
            # 清屏
            print("\033[2J\033[H")
            print("=== 📊 Fintellic 财报处理监控面板 ===")
            print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            # 状态统计
            stats = db.query(
                Filing.status,
                func.count(Filing.id).label('count')
            ).group_by(Filing.status).all()
            
            total = sum(count for _, count in stats)
            print(f"📈 状态统计 (总计: {total}):")
            for status, count in sorted(stats, key=lambda x: x[1], reverse=True):
                # 添加图标
                icon = {
                    ProcessingStatus.COMPLETED: "✅",
                    ProcessingStatus.PENDING: "⏳",
                    ProcessingStatus.FAILED: "❌",
                    ProcessingStatus.DOWNLOADING: "⬇️",
                    ProcessingStatus.PARSING: "📄",
                    ProcessingStatus.AI_PROCESSING: "🤖"
                }.get(status, "❓")
                
                bar_length = int(count / max(total, 1) * 30)
                bar = "█" * bar_length + "░" * (30 - bar_length)
                print(f"  {icon} {status.value:15} [{bar}] {count:3d}")
            
            # 今日进度
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_completed = db.query(Filing).filter(
                Filing.status == ProcessingStatus.COMPLETED,
                Filing.updated_at >= today
            ).count()
            
            today_new = db.query(Filing).filter(
                Filing.created_at >= today
            ).count()
            
            print(f"\n📅 今日进度:")
            print(f"  新增财报: {today_new}")
            print(f"  完成处理: {today_completed}")
            
            # 成功率
            if total > 0:
                success_rate = (stats[0][1] if stats[0][0] == ProcessingStatus.COMPLETED else 0) / total * 100
                print(f"  成功率: {success_rate:.1f}%")
            
            # 最近完成的
            recent_completed = db.query(Filing).filter(
                Filing.status == ProcessingStatus.COMPLETED
            ).order_by(desc(Filing.updated_at)).limit(5).all()
            
            if recent_completed:
                print("\n✅ 最近完成:")
                for f in recent_completed:
                    if f.updated_at:
                        time_str = f.updated_at.strftime('%H:%M:%S')
                    else:
                        time_str = "N/A"
                    
                    # 显示 AI 摘要的前50个字符
                    summary = ""
                    if f.ai_summary:
                        summary = f" - {f.ai_summary[:50]}..."
                    
                    print(f"  {f.company.ticker:6} {f.filing_type.value:5} ({time_str}){summary}")
            
            # 正在处理
            processing = db.query(Filing).filter(
                Filing.status.in_([
                    ProcessingStatus.DOWNLOADING,
                    ProcessingStatus.PARSING,
                    ProcessingStatus.AI_PROCESSING
                ])
            ).all()
            
            if processing:
                print(f"\n⚙️  正在处理 ({len(processing)}):")
                for f in processing:
                    print(f"  {f.company.ticker:6} {f.filing_type.value:5} - {f.status.value}")
            
            # 最近的错误
            recent_errors = db.query(Filing).filter(
                Filing.status == ProcessingStatus.FAILED,
                Filing.updated_at >= datetime.now() - timedelta(hours=1)
            ).limit(3).all()
            
            if recent_errors:
                print(f"\n❌ 最近的错误:")
                for f in recent_errors:
                    error_msg = f.error_message[:50] + "..." if f.error_message and len(f.error_message) > 50 else f.error_message
                    print(f"  {f.company.ticker:6} - {error_msg}")
            
            print("\n" + "="*50)
            print("按 Ctrl+C 退出 | 每5秒自动刷新")
            
        except KeyboardInterrupt:
            print("\n\n👋 退出监控")
            break
        except Exception as e:
            print(f"错误: {e}")
        finally:
            db.close()
        
        time.sleep(5)  # 每5秒刷新

if __name__ == "__main__":
    print("启动监控...")
    monitor()

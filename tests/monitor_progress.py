#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import time
from app.core.database import SessionLocal
from app.models import Filing, ProcessingStatus
from datetime import datetime, timedelta

def monitor():
    while True:
        db = SessionLocal()
        try:
            # 清屏
            print("\033[2J\033[H")
            print("=== 财报处理监控面板 ===")
            print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            # 状态统计
            from sqlalchemy import func
            stats = db.query(
                Filing.status,
                func.count(Filing.id).label('count')
            ).group_by(Filing.status).all()
            
            print("状态统计:")
            for status, count in stats:
                print(f"  {status.value:15} : {count:3d}")
            
            # 今日进度
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_completed = db.query(Filing).filter(
                Filing.status == ProcessingStatus.COMPLETED,
                Filing.updated_at >= today
            ).count()
            
            today_new = db.query(Filing).filter(
                Filing.created_at >= today
            ).count()
            
            print(f"\n今日进度:")
            print(f"  新增: {today_new}")
            print(f"  完成: {today_completed}")
            
            # 最近完成的
            recent_completed = db.query(Filing).filter(
                Filing.status == ProcessingStatus.COMPLETED
            ).order_by(Filing.updated_at.desc()).limit(5).all()
            
            if recent_completed:
                print("\n最近完成:")
                for f in recent_completed:
                    print(f"  {f.company.ticker:6} {f.filing_type.value:5} - {f.updated_at.strftime('%H:%M:%S')}")
            
            # 正在处理
            processing = db.query(Filing).filter(
                Filing.status.in_([
                    ProcessingStatus.DOWNLOADING,
                    ProcessingStatus.PARSING,
                    ProcessingStatus.AI_PROCESSING
                ])
            ).all()
            
            if processing:
                print(f"\n正在处理 ({len(processing)}):")
                for f in processing:
                    print(f"  {f.company.ticker:6} {f.filing_type.value:5} - {f.status.value}")
            
            print("\n按 Ctrl+C 退出")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"错误: {e}")
        finally:
            db.close()
        
        time.sleep(5)  # 每5秒刷新

if __name__ == "__main__":
    print("启动监控...")
    monitor()

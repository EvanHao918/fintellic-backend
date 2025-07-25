#!/usr/bin/env python3
"""
检查财报处理状态
实时显示各种财报的处理情况
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus, FilingType
from app.models.company import Company
from datetime import datetime, timedelta
import time


def get_status_summary(db: Session):
    """获取状态汇总"""
    # 按状态统计
    status_counts = db.query(
        Filing.status,
        func.count(Filing.id).label('count')
    ).group_by(Filing.status).all()
    
    # 按类型统计
    type_counts = db.query(
        Filing.filing_type,
        func.count(Filing.id).label('count')
    ).group_by(Filing.filing_type).all()
    
    # 按类型和状态统计
    type_status_counts = db.query(
        Filing.filing_type,
        Filing.status,
        func.count(Filing.id).label('count')
    ).group_by(Filing.filing_type, Filing.status).all()
    
    return status_counts, type_counts, type_status_counts


def get_recent_activity(db: Session, minutes=10):
    """获取最近的活动"""
    since = datetime.utcnow() - timedelta(minutes=minutes)
    
    recent_completed = db.query(Filing).join(Company).filter(
        Filing.processing_completed_at >= since,
        Filing.status == ProcessingStatus.COMPLETED
    ).order_by(Filing.processing_completed_at.desc()).limit(5).all()
    
    recent_failed = db.query(Filing).join(Company).filter(
        Filing.processing_completed_at >= since,
        Filing.status == ProcessingStatus.FAILED
    ).order_by(Filing.processing_completed_at.desc()).limit(5).all()
    
    currently_processing = db.query(Filing).join(Company).filter(
        Filing.status.in_([ProcessingStatus.DOWNLOADING, ProcessingStatus.PARSING])
    ).all()
    
    return recent_completed, recent_failed, currently_processing


def check_content_quality(db: Session):
    """检查内容质量"""
    # 获取已完成的财报
    completed_filings = db.query(Filing).filter(
        Filing.status == ProcessingStatus.COMPLETED
    ).all()
    
    quality_issues = {
        'no_summary': [],
        'short_summary': [],
        'no_questions': [],
        'no_specialized': []
    }
    
    for filing in completed_filings:
        if not filing.ai_summary:
            quality_issues['no_summary'].append(filing)
        elif len(filing.ai_summary) < 100:
            quality_issues['short_summary'].append(filing)
        
        if not filing.key_questions:
            quality_issues['no_questions'].append(filing)
        
        # 检查专门字段
        if filing.filing_type == FilingType.FORM_8K and not filing.event_nature_analysis:
            quality_issues['no_specialized'].append(filing)
        elif filing.filing_type == FilingType.FORM_10K and not filing.market_impact_10k:
            quality_issues['no_specialized'].append(filing)
        elif filing.filing_type == FilingType.FORM_10Q and not filing.market_impact_10q:
            quality_issues['no_specialized'].append(filing)
    
    return quality_issues


def display_dashboard():
    """显示仪表板"""
    db = SessionLocal()
    
    try:
        while True:
            # 清屏
            print("\033[2J\033[H")  # ANSI escape codes
            
            print("=" * 80)
            print("📊 Fintellic 财报处理状态仪表板")
            print("=" * 80)
            print(f"🕐 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print()
            
            # 1. 状态汇总
            status_counts, type_counts, type_status_counts = get_status_summary(db)
            
            print("📈 整体状态统计:")
            print("-" * 40)
            total = sum(count for _, count in status_counts)
            for status, count in sorted(status_counts, key=lambda x: x[0].value):
                percentage = (count / total * 100) if total > 0 else 0
                bar = "█" * int(percentage / 2)
                print(f"  {status.value:<15} {count:>4} ({percentage:>5.1f}%) {bar}")
            print(f"  {'TOTAL':<15} {total:>4}")
            print()
            
            # 2. 按类型统计
            print("📋 按财报类型统计:")
            print("-" * 60)
            print(f"  {'Type':<8} {'Total':<8} {'Complete':<10} {'Failed':<8} {'Pending':<8}")
            print("-" * 60)
            
            # 构建类型状态矩阵
            type_status_matrix = {}
            for filing_type, status, count in type_status_counts:
                if filing_type not in type_status_matrix:
                    type_status_matrix[filing_type] = {}
                type_status_matrix[filing_type][status] = count
            
            for filing_type, total_count in sorted(type_counts, key=lambda x: x[0].value):
                completed = type_status_matrix.get(filing_type, {}).get(ProcessingStatus.COMPLETED, 0)
                failed = type_status_matrix.get(filing_type, {}).get(ProcessingStatus.FAILED, 0)
                pending = type_status_matrix.get(filing_type, {}).get(ProcessingStatus.PENDING, 0)
                
                success_rate = (completed / total_count * 100) if total_count > 0 else 0
                print(f"  {filing_type.value:<8} {total_count:<8} "
                      f"{completed:<10} {failed:<8} {pending:<8} "
                      f"[{success_rate:>5.1f}% ✅]")
            print()
            
            # 3. 最近活动
            recent_completed, recent_failed, currently_processing = get_recent_activity(db)
            
            if currently_processing:
                print(f"⚡ 正在处理 ({len(currently_processing)} 个):")
                print("-" * 40)
                for filing in currently_processing[:5]:
                    print(f"  • {filing.company.ticker:<6} {filing.filing_type.value:<8} "
                          f"状态: {filing.status.value}")
                print()
            
            if recent_completed:
                print(f"✅ 最近完成 (10分钟内):")
                print("-" * 40)
                for filing in recent_completed:
                    duration = (filing.processing_completed_at - filing.processing_started_at).seconds
                    print(f"  • {filing.company.ticker:<6} {filing.filing_type.value:<8} "
                          f"耗时: {duration}秒")
            
            if recent_failed:
                print(f"\n❌ 最近失败 (10分钟内):")
                print("-" * 40)
                for filing in recent_failed:
                    error_msg = (filing.error_message or "Unknown error")[:40]
                    print(f"  • {filing.company.ticker:<6} {filing.filing_type.value:<8} "
                          f"错误: {error_msg}")
            
            # 4. 内容质量检查
            quality_issues = check_content_quality(db)
            
            print(f"\n📝 内容质量检查:")
            print("-" * 40)
            print(f"  • 缺少摘要: {len(quality_issues['no_summary'])} 个")
            print(f"  • 摘要过短: {len(quality_issues['short_summary'])} 个")
            print(f"  • 缺少问答: {len(quality_issues['no_questions'])} 个")
            print(f"  • 缺少专门分析: {len(quality_issues['no_specialized'])} 个")
            
            print("\n" + "=" * 80)
            print("按 Ctrl+C 退出 | 自动刷新间隔: 5秒")
            
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n👋 退出监控")
    finally:
        db.close()


if __name__ == "__main__":
    display_dashboard()
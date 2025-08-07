#!/usr/bin/env python3
"""
检查财报处理状态
实时显示各种财报的处理情况
修复：移除对不存在的 key_questions 字段的检查
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
    
    # 只使用数据库中确实存在的状态值
    currently_processing = db.query(Filing).join(Company).filter(
        Filing.status.in_([ProcessingStatus.DOWNLOADING, ProcessingStatus.PARSING])
    ).all()
    
    return recent_completed, recent_failed, currently_processing


def check_content_quality(db: Session):
    """检查内容质量 - 基于实际存在的字段"""
    # 获取已完成的财报
    completed_filings = db.query(Filing).filter(
        Filing.status == ProcessingStatus.COMPLETED
    ).all()
    
    quality_issues = {
        'no_unified_analysis': [],  # 新的统一分析字段
        'no_ai_summary': [],        # 旧的AI摘要字段
        'short_summary': [],
        'no_feed_summary': [],       # Feed摘要
        'no_specialized': [],
        'low_score': []             # 评分过低
    }
    
    for filing in completed_filings:
        # 检查统一分析（新系统）
        if not filing.unified_analysis:
            quality_issues['no_unified_analysis'].append(filing)
        
        # 检查AI摘要（旧系统）
        if not filing.ai_summary:
            quality_issues['no_ai_summary'].append(filing)
        elif filing.ai_summary and len(filing.ai_summary) < 100:
            quality_issues['short_summary'].append(filing)
        
        # 检查Feed摘要
        if not filing.unified_feed_summary:
            quality_issues['no_feed_summary'].append(filing)
        
        # 检查评分
        if filing.unified_score and filing.unified_score < 50:
            quality_issues['low_score'].append(filing)
        
        # 检查各类型专门字段
        if filing.filing_type == FilingType.FORM_8K:
            if not filing.event_nature_analysis and not filing.event_impact_analysis:
                quality_issues['no_specialized'].append(filing)
        elif filing.filing_type == FilingType.FORM_10K:
            if not filing.market_impact_10k and not filing.annual_business_overview:
                quality_issues['no_specialized'].append(filing)
        elif filing.filing_type == FilingType.FORM_10Q:
            if not filing.market_impact_10q and not filing.quarterly_performance:
                quality_issues['no_specialized'].append(filing)
        elif filing.filing_type == FilingType.FORM_S1:
            if not filing.ipo_company_overview and not filing.company_overview:
                quality_issues['no_specialized'].append(filing)
    
    return quality_issues


def get_processing_stats(db: Session):
    """获取处理统计信息"""
    # 今日处理统计
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    today_stats = db.query(
        Filing.status,
        func.count(Filing.id).label('count')
    ).filter(
        Filing.created_at >= today_start
    ).group_by(Filing.status).all()
    
    # 计算平均处理时间
    avg_processing_time = db.query(
        func.avg(
            func.extract('epoch', Filing.processing_completed_at - Filing.processing_started_at)
        ).label('avg_seconds')
    ).filter(
        Filing.status == ProcessingStatus.COMPLETED,
        Filing.processing_completed_at.isnot(None),
        Filing.processing_started_at.isnot(None)
    ).scalar()
    
    return today_stats, avg_processing_time


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
                
                # 根据状态设置颜色（可选）
                status_display = status.value
                if status == ProcessingStatus.COMPLETED:
                    status_display = f"✅ {status.value}"
                elif status == ProcessingStatus.FAILED:
                    status_display = f"❌ {status.value}"
                elif status in [ProcessingStatus.DOWNLOADING, ProcessingStatus.PARSING]:
                    status_display = f"⚡ {status.value}"
                elif status == ProcessingStatus.PENDING:
                    status_display = f"⏳ {status.value}"
                
                print(f"  {status_display:<20} {count:>4} ({percentage:>5.1f}%) {bar}")
            print(f"  {'TOTAL':<20} {total:>4}")
            print()
            
            # 2. 按类型统计
            print("📋 按财报类型统计:")
            print("-" * 70)
            print(f"  {'Type':<8} {'Total':<8} {'Complete':<10} {'Failed':<8} {'Pending':<8} {'Success Rate':<12}")
            print("-" * 70)
            
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
                downloading = type_status_matrix.get(filing_type, {}).get(ProcessingStatus.DOWNLOADING, 0)
                parsing = type_status_matrix.get(filing_type, {}).get(ProcessingStatus.PARSING, 0)
                
                # 将下载中和解析中的也算作pending
                pending = pending + downloading + parsing
                
                success_rate = (completed / total_count * 100) if total_count > 0 else 0
                
                # 根据成功率设置指示器
                if success_rate >= 95:
                    indicator = "🟢"
                elif success_rate >= 80:
                    indicator = "🟡"
                else:
                    indicator = "🔴"
                
                print(f"  {filing_type.value:<8} {total_count:<8} "
                      f"{completed:<10} {failed:<8} {pending:<8} "
                      f"{indicator} {success_rate:>5.1f}%")
            print()
            
            # 3. 今日处理统计
            today_stats, avg_time = get_processing_stats(db)
            if today_stats:
                print("📅 今日处理统计:")
                print("-" * 40)
                today_total = sum(count for _, count in today_stats)
                for status, count in today_stats:
                    print(f"  • {status.value:<15}: {count} 个")
                print(f"  • 总计: {today_total} 个")
                if avg_time:
                    print(f"  • 平均处理时间: {int(avg_time)}秒")
                print()
            
            # 4. 最近活动
            recent_completed, recent_failed, currently_processing = get_recent_activity(db)
            
            if currently_processing:
                print(f"⚡ 正在处理 ({len(currently_processing)} 个):")
                print("-" * 40)
                for filing in currently_processing[:5]:
                    elapsed = ""
                    if filing.processing_started_at:
                        elapsed_seconds = (datetime.utcnow() - filing.processing_started_at).seconds
                        elapsed = f"(已运行 {elapsed_seconds}秒)"
                    print(f"  • {filing.company.ticker:<6} {filing.filing_type.value:<8} "
                          f"状态: {filing.status.value} {elapsed}")
                if len(currently_processing) > 5:
                    print(f"  ... 还有 {len(currently_processing) - 5} 个正在处理")
                print()
            
            if recent_completed:
                print(f"✅ 最近完成 (10分钟内):")
                print("-" * 40)
                for filing in recent_completed:
                    if filing.processing_completed_at and filing.processing_started_at:
                        duration = (filing.processing_completed_at - filing.processing_started_at).seconds
                        print(f"  • {filing.company.ticker:<6} {filing.filing_type.value:<8} "
                              f"耗时: {duration}秒")
                    else:
                        print(f"  • {filing.company.ticker:<6} {filing.filing_type.value:<8}")
            
            if recent_failed:
                print(f"\n❌ 最近失败 (10分钟内):")
                print("-" * 40)
                for filing in recent_failed:
                    error_msg = (filing.error_message or "Unknown error")[:40]
                    print(f"  • {filing.company.ticker:<6} {filing.filing_type.value:<8} "
                          f"错误: {error_msg}")
            
            # 5. 内容质量检查
            quality_issues = check_content_quality(db)
            
            print(f"\n📝 内容质量检查:")
            print("-" * 40)
            
            # 显示分析版本情况
            v2_count = db.query(func.count(Filing.id)).filter(
                Filing.analysis_version == 'v2',
                Filing.status == ProcessingStatus.COMPLETED
            ).scalar() or 0
            
            v1_count = db.query(func.count(Filing.id)).filter(
                Filing.analysis_version != 'v2',
                Filing.status == ProcessingStatus.COMPLETED
            ).scalar() or 0
            
            print(f"  📊 分析版本:")
            print(f"     • 统一分析(v2): {v2_count} 个")
            print(f"     • 旧版分析(v1): {v1_count} 个")
            print()
            
            print(f"  ⚠️ 质量问题:")
            print(f"     • 缺少统一分析: {len(quality_issues['no_unified_analysis'])} 个")
            print(f"     • 缺少AI摘要: {len(quality_issues['no_ai_summary'])} 个")
            print(f"     • 摘要过短: {len(quality_issues['short_summary'])} 个")
            print(f"     • 缺少Feed摘要: {len(quality_issues['no_feed_summary'])} 个")
            print(f"     • 缺少专门分析: {len(quality_issues['no_specialized'])} 个")
            print(f"     • 评分过低(<50): {len(quality_issues['low_score'])} 个")
            
            print("\n" + "=" * 80)
            print("按 Ctrl+C 退出 | 自动刷新间隔: 5秒")
            
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n👋 退出监控")
    except Exception as e:
        print(f"\n❌ 发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    display_dashboard()
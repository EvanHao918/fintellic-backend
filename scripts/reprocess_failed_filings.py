#!/usr/bin/env python3
"""
重新处理失败和卡住的财报
包括：FAILED, PENDING, PARSING, DOWNLOADING 状态的财报
FIXED: 处理ticker为None的情况
NEW: 添加按日期重新处理所有财报的功能（选项6和命令行参数）
"""

import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
from app.tasks.filing_tasks import process_filing_task
from datetime import datetime, timedelta
import logging
import argparse

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_failed_filings(db: Session):
    """获取所有失败的财报"""
    return db.query(Filing).filter(
        Filing.status == ProcessingStatus.FAILED
    ).all()


def get_pending_filings(db: Session):
    """获取所有待处理的财报"""
    return db.query(Filing).filter(
        Filing.status == ProcessingStatus.PENDING
    ).all()


def get_stuck_filings(db: Session, stuck_minutes=30):
    """获取卡住的财报（parsing或downloading状态超过指定时间）"""
    stuck_time = datetime.utcnow() - timedelta(minutes=stuck_minutes)
    
    stuck_filings = db.query(Filing).filter(
        Filing.status.in_([ProcessingStatus.PARSING, ProcessingStatus.DOWNLOADING])
    ).all()
    
    # 过滤出真正卡住的（处理时间过长的）
    truly_stuck = []
    for filing in stuck_filings:
        if filing.processing_started_at:
            # 处理时区问题
            if filing.processing_started_at.tzinfo is None:
                # naive datetime，假设是UTC
                processing_started_utc = filing.processing_started_at
            else:
                # aware datetime，转换为UTC
                processing_started_utc = filing.processing_started_at.replace(tzinfo=None)
            
            if processing_started_utc < stuck_time:
                truly_stuck.append(filing)
        else:
            # 没有开始时间但状态是processing，也算卡住
            truly_stuck.append(filing)
    
    return truly_stuck


def get_incomplete_filings(db: Session):
    """获取内容不完整的财报"""
    completed = db.query(Filing).filter(
        Filing.status == ProcessingStatus.COMPLETED
    ).all()
    
    incomplete = []
    for filing in completed:
        # 检查是否有基本的分析内容
        has_content = False
        
        # 检查新版统一分析
        if filing.unified_analysis and len(filing.unified_analysis) > 100:
            has_content = True
        # 检查旧版AI摘要
        elif filing.ai_summary and len(filing.ai_summary) > 100:
            has_content = True
        
        if not has_content:
            incomplete.append(filing)
    
    return incomplete


def get_filings_by_date(db: Session, target_date: datetime):
    """
    NEW: 获取指定日期的所有财报（基于 detected_at - 系统检测时间）
    Args:
        db: 数据库会话
        target_date: 目标日期（可以是字符串 'YYYY-MM-DD' 或 datetime 对象）
    Returns:
        该日期的所有 filing 列表
    """
    from sqlalchemy import func
    
    # 如果传入的是字符串，转换为 datetime
    if isinstance(target_date, str):
        try:
            target_date = datetime.strptime(target_date, '%Y-%m-%d')
        except ValueError:
            logger.error(f"Invalid date format: {target_date}. Expected YYYY-MM-DD")
            return []
    
    # 使用 DATE() 函数直接比较日期部分（忽略时区问题）
    date_str = target_date.strftime('%Y-%m-%d')
    
    filings = db.query(Filing).filter(
        func.date(Filing.detected_at) == date_str
    ).order_by(Filing.detected_at.desc()).all()
    
    return filings


async def reprocess_filing(filing_id: int):
    """重新处理单个财报"""
    try:
        logger.info(f"Queueing filing ID {filing_id} for reprocessing")
        process_filing_task.delay(filing_id)
        return True
    except Exception as e:
        logger.error(f"Error reprocessing filing {filing_id}: {e}")
        return False


def get_display_ticker(filing):
    """获取用于显示的ticker，处理None的情况"""
    if filing.ticker:
        return filing.ticker
    elif filing.company and filing.company.ticker:
        return filing.company.ticker
    elif filing.company and filing.company.cik:
        # 对于没有ticker的公司（如S-1），显示CIK后4位
        return f"CIK-{filing.company.cik[-4:]}"
    else:
        return "N/A"


def get_company_name(filing):
    """获取公司名称，处理None的情况"""
    if filing.company and filing.company.name:
        # 截取前20个字符
        return filing.company.name[:20]
    else:
        return "Unknown"


def display_filings_by_date_stats(filings, target_date):
    """
    NEW: 显示指定日期财报的统计信息（基于 detected_at）
    """
    if not filings:
        print(f"\n❌ {target_date.strftime('%Y-%m-%d')} 没有找到任何财报")
        return
    
    print(f"\n📊 {target_date.strftime('%Y-%m-%d')} 的财报统计 (基于系统检测时间):")
    print("="*80)
    
    # 统计各状态数量
    status_counts = {}
    for filing in filings:
        status = filing.status.value
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # 统计各类型数量
    type_counts = {}
    for filing in filings:
        ftype = filing.filing_type.value
        type_counts[ftype] = type_counts.get(ftype, 0) + 1
    
    print(f"\n总数: {len(filings)} 个财报")
    
    print(f"\n按状态分布:")
    for status, count in sorted(status_counts.items()):
        print(f"  • {status}: {count} 个")
    
    print(f"\n按类型分布:")
    for ftype, count in sorted(type_counts.items()):
        print(f"  • {ftype}: {count} 个")
    
    # 显示前10个财报详情
    print(f"\n前 10 个财报详情:")
    print("-" * 100)
    print(f"{'ID':<8} {'Ticker':<10} {'Type':<8} {'Detected Time':<16} {'Status':<15} {'Has Analysis':<15}")
    print("-" * 100)
    
    for filing in filings[:10]:
        display_ticker = get_display_ticker(filing)
        has_analysis = "✓ Yes" if (filing.unified_analysis and len(filing.unified_analysis) > 100) else "✗ No"
        detected_time = filing.detected_at.strftime('%H:%M:%S') if filing.detected_at else "N/A"
        
        print(f"{filing.id:<8} {display_ticker:<10} {filing.filing_type.value:<8} "
              f"{detected_time:<16} {filing.status.value:<15} {has_analysis:<15}")
    
    if len(filings) > 10:
        print(f"\n... 还有 {len(filings) - 10} 个财报")
    
    print("-" * 100)


async def main():
    """主函数"""
    # NEW: 添加命令行参数支持
    parser = argparse.ArgumentParser(
        description='重新处理财报 - 支持按状态或按日期处理',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 交互式模式（原有功能）
  python scripts/reprocess_failed_filings.py
  
  # 按日期重新处理所有财报
  python scripts/reprocess_failed_filings.py --date 2025-10-27
  
  # 按日期重新处理，只处理已完成的财报
  python scripts/reprocess_failed_filings.py --date 2025-10-27 --completed-only
        """
    )
    parser.add_argument(
        '--date',
        type=str,
        help='按日期重新处理所有财报 (格式: YYYY-MM-DD，例如: 2025-10-27)'
    )
    parser.add_argument(
        '--completed-only',
        action='store_true',
        help='只重新处理已完成状态的财报（配合 --date 使用）'
    )
    
    args = parser.parse_args()
    
    db = SessionLocal()
    
    try:
        # NEW: 如果提供了 --date 参数，直接处理该日期的财报
        if args.date:
            try:
                target_date = datetime.strptime(args.date, '%Y-%m-%d')
            except ValueError:
                print(f"\n❌ 错误: 日期格式不正确。请使用 YYYY-MM-DD 格式，例如: 2025-10-27")
                return
            
            print("\n" + "="*80)
            print(f"📅 按日期重新处理财报: {args.date}")
            print("="*80)
            
            # 获取该日期的所有财报
            filings = get_filings_by_date(db, target_date)
            
            if not filings:
                print(f"\n❌ {args.date} 没有找到任何财报")
                return
            
            # 如果指定了 --completed-only，只保留已完成的
            if args.completed_only:
                filings = [f for f in filings if f.status == ProcessingStatus.COMPLETED]
                print(f"\n✓ 只处理已完成状态的财报")
            
            # 显示统计信息
            display_filings_by_date_stats(filings, target_date)
            
            # 确认是否继续
            print(f"\n⚠️  即将重新处理 {len(filings)} 个财报")
            print(f"   这将重置它们的状态并重新运行 AI 分析")
            response = input("\n确认继续? (y/n): ")
            if response.lower() != 'y':
                print("❌ 已取消")
                return
            
            # 重新处理
            print("\n🚀 开始重新处理...")
            success_count = 0
            
            for i, filing in enumerate(filings, 1):
                try:
                    # 重置状态为PENDING
                    filing.status = ProcessingStatus.PENDING
                    filing.error_message = None
                    filing.retry_count = 0
                    filing.processing_started_at = None
                    filing.processing_completed_at = None
                    
                    # 可选：清空分析内容，强制重新分析
                    filing.unified_analysis = None
                    filing.analysis_version = None
                    
                    db.commit()
                    
                    # 加入处理队列
                    await reprocess_filing(filing.id)
                    
                    display_ticker = get_display_ticker(filing)
                    print(f"  [{i}/{len(filings)}] ✅ {display_ticker} {filing.filing_type.value} "
                          f"(ID: {filing.id}) 已加入队列")
                    success_count += 1
                    
                    # 每5个暂停一下，避免过载
                    if i % 5 == 0:
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    display_ticker = get_display_ticker(filing)
                    print(f"  [{i}/{len(filings)}] ❌ {display_ticker} 处理失败: {e}")
            
            print("\n" + "="*80)
            print(f"✅ 完成！成功加入队列: {success_count}/{len(filings)} 个财报")
            print("="*80)
            print("\n📊 后续监控:")
            print("  1. 查看状态: python scripts/check_filing_status.py")
            print("  2. 查看日志: tail -f logs/fintellic.log | grep -E 'ERROR|WARNING|succeeded'")
            
            return
        
        # 原有的交互式流程（没有提供 --date 参数时）
        print("\n" + "="*80)
        print("📊 财报处理状态检查")
        print("="*80)
        
        # 1. 获取各种状态的财报
        failed_filings = get_failed_filings(db)
        pending_filings = get_pending_filings(db)
        stuck_filings = get_stuck_filings(db, stuck_minutes=30)
        incomplete_filings = get_incomplete_filings(db)
        
        print(f"\n📈 发现的问题财报:")
        print(f"  • 失败 (FAILED): {len(failed_filings)} 个")
        print(f"  • 待处理 (PENDING): {len(pending_filings)} 个")
        print(f"  • 卡住 (PARSING/DOWNLOADING >30分钟): {len(stuck_filings)} 个")
        print(f"  • 内容不完整 (COMPLETED但无内容): {len(incomplete_filings)} 个")
        
        # 2. 合并所有需要处理的财报（去重）
        all_filings_dict = {}
        
        for filing in failed_filings:
            all_filings_dict[filing.id] = ('FAILED', filing)
        
        for filing in pending_filings:
            if filing.id not in all_filings_dict:
                all_filings_dict[filing.id] = ('PENDING', filing)
        
        for filing in stuck_filings:
            if filing.id not in all_filings_dict:
                all_filings_dict[filing.id] = ('STUCK', filing)
        
        for filing in incomplete_filings:
            if filing.id not in all_filings_dict:
                all_filings_dict[filing.id] = ('INCOMPLETE', filing)
        
        all_filings_to_reprocess = list(all_filings_dict.values())
        
        if not all_filings_to_reprocess:
            print("\n✅ 没有需要重新处理的财报！")
            # NEW: 提示可以使用日期选项
            print("\n💡 提示: 如果要按日期重新处理财报，可以使用:")
            print("   python scripts/reprocess_failed_filings.py --date YYYY-MM-DD")
            return
        
        # 3. 显示详细信息
        print(f"\n📋 将要重新处理 {len(all_filings_to_reprocess)} 个财报：")
        print("-" * 100)
        print(f"{'ID':<8} {'Ticker':<10} {'Type':<8} {'Date':<12} {'Current Status':<15} {'Issue':<30}")
        print("-" * 100)
        
        # 按问题类型排序显示
        for reason, filing in sorted(all_filings_to_reprocess, key=lambda x: x[0]):
            issue_desc = {
                'FAILED': f"处理失败: {(filing.error_message or 'Unknown')[:25]}",
                'PENDING': "等待处理",
                'STUCK': f"卡在 {filing.status.value} 状态",
                'INCOMPLETE': "已完成但无内容"
            }.get(reason, reason)
            
            # FIXED: 使用安全的方式获取ticker
            display_ticker = get_display_ticker(filing)
            
            print(f"{filing.id:<8} {display_ticker:<10} {filing.filing_type.value:<8} "
                  f"{filing.filing_date.strftime('%Y-%m-%d'):<12} "
                  f"{filing.status.value:<15} {issue_desc:<30}")
        
        print("-" * 100)
        
        # 显示失败财报的详细信息
        if failed_filings:
            print("\n📝 失败财报详细信息:")
            print("-" * 100)
            for filing in failed_filings[:10]:  # 只显示前10个
                display_ticker = get_display_ticker(filing)
                company_name = get_company_name(filing)
                print(f"\nID: {filing.id}")
                print(f"  公司: {company_name} ({display_ticker})")
                print(f"  类型: {filing.filing_type.value}")
                print(f"  日期: {filing.filing_date.strftime('%Y-%m-%d')}")
                print(f"  错误: {filing.error_message or 'No error message'}")
                if filing.company:
                    print(f"  CIK: {filing.company.cik}")
                    print(f"  是S-1: {'是' if filing.filing_type.value == 'S-1' else '否'}")
        
        # 4. 显示处理选项
        print("\n🔧 处理选项:")
        print("  1. 处理所有问题财报")
        print("  2. 只处理失败的 (FAILED)")
        print("  3. 只处理卡住的 (STUCK)")
        print("  4. 只处理待处理的 (PENDING)")
        print("  5. 只处理内容不完整的")
        print("  6. 按日期重新处理所有财报 (NEW)")
        print("  0. 取消")
        
        choice = input("\n请选择 (0-6): ").strip()
        
        if choice == '0':
            print("❌ 已取消")
            return
        elif choice == '2':
            filings_to_process = [(r, f) for r, f in all_filings_to_reprocess if r == 'FAILED']
        elif choice == '3':
            filings_to_process = [(r, f) for r, f in all_filings_to_reprocess if r == 'STUCK']
        elif choice == '4':
            filings_to_process = [(r, f) for r, f in all_filings_to_reprocess if r == 'PENDING']
        elif choice == '5':
            filings_to_process = [(r, f) for r, f in all_filings_to_reprocess if r == 'INCOMPLETE']
        elif choice == '6':
            # NEW: 按日期重新处理
            date_input = input("\n请输入日期 (YYYY-MM-DD，例如 2025-10-27): ").strip()
            try:
                target_date = datetime.strptime(date_input, '%Y-%m-%d')
            except ValueError:
                print("\n❌ 错误: 日期格式不正确。请使用 YYYY-MM-DD 格式")
                return
            
            print(f"\n正在查询 {date_input} 的财报...")
            date_filings = get_filings_by_date(db, target_date)
            
            if not date_filings:
                print(f"\n❌ {date_input} 没有找到任何财报")
                return
            
            # 显示统计信息
            display_filings_by_date_stats(date_filings, target_date)
            
            # 询问是否只处理已完成的
            completed_only = input("\n是否只重新处理已完成状态的财报? (y/n): ").strip().lower()
            if completed_only == 'y':
                date_filings = [f for f in date_filings if f.status == ProcessingStatus.COMPLETED]
                print(f"\n✓ 只处理已完成状态的财报，共 {len(date_filings)} 个")
            
            # 转换为统一格式
            filings_to_process = [('DATE_REPROCESS', f) for f in date_filings]
        else:
            filings_to_process = all_filings_to_reprocess
        
        if not filings_to_process:
            print("❌ 没有符合条件的财报")
            return
        
        # 5. 最终确认
        print(f"\n⚠️  即将重新处理 {len(filings_to_process)} 个财报")
        response = input("确认继续? (y/n): ")
        if response.lower() != 'y':
            print("❌ 已取消")
            return
        
        # 6. 重置状态并重新处理
        print("\n🚀 开始重新处理...")
        
        for i, (reason, filing) in enumerate(filings_to_process, 1):
            try:
                # 重置状态为PENDING
                filing.status = ProcessingStatus.PENDING
                filing.error_message = None
                filing.retry_count = 0
                filing.processing_started_at = None
                filing.processing_completed_at = None
                
                # 如果是按日期重新处理，清空分析内容
                if reason == 'DATE_REPROCESS':
                    filing.unified_analysis = None
                    filing.analysis_version = None
                
                db.commit()
                
                # 加入处理队列
                await reprocess_filing(filing.id)
                
                display_ticker = get_display_ticker(filing)
                print(f"  [{i}/{len(filings_to_process)}] ✅ {display_ticker} {filing.filing_type.value} "
                      f"(ID: {filing.id}) 已加入队列")
                
                # 每5个暂停一下，避免过载
                if i % 5 == 0:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                display_ticker = get_display_ticker(filing)
                print(f"  [{i}/{len(filings_to_process)}] ❌ {display_ticker} 处理失败: {e}")
        
        print("\n" + "="*80)
        print("✅ 所有财报已加入处理队列！")
        print("="*80)
        print("\n📊 后续监控:")
        print("  1. 查看状态: python scripts/check_filing_status.py")
        print("  2. 查看日志: tail -f logs/fintellic.log | grep -E 'ERROR|WARNING|succeeded'")
        print("  3. 查看Celery: tail -f celery_worker.log")
        print("  4. 查看数据库:")
        print("     psql fintellic_db -c \"SELECT id, ticker, filing_type, status, error_message FROM filings WHERE status != 'completed' ORDER BY id DESC LIMIT 20;\"")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
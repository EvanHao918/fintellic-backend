#!/usr/bin/env python
"""
批量重处理失败和待处理的财报
用于修复历史遗留问题
"""
import asyncio
import logging
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import select
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models.filing import Filing, ProcessingStatus, FilingType
from app.models.company import Company
from app.services.ai_processor import ai_processor
from app.core.config import settings
from app.core.database import engine

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建数据库会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


async def process_single_filing(db: Session, filing: Filing) -> bool:
    """处理单个财报"""
    try:
        logger.info(f"开始处理: {filing.company.ticker} - {filing.filing_type.value} - {filing.filing_date}")
        
        # 调用 AI 处理器
        success = await ai_processor.process_filing(db, filing)
        
        if success:
            logger.info(f"✅ 成功处理: {filing.accession_number}")
            # 检查是否生成了市场影响分析
            if filing.filing_type == FilingType.FORM_10K and filing.market_impact_10k:
                logger.info("  - 已生成 10-K 市场影响分析")
            elif filing.filing_type == FilingType.FORM_10Q and filing.market_impact_10q:
                logger.info("  - 已生成 10-Q 市场影响分析")
        else:
            logger.error(f"❌ 处理失败: {filing.accession_number}")
            
        return success
        
    except Exception as e:
        logger.error(f"处理出错 {filing.accession_number}: {str(e)}")
        filing.status = ProcessingStatus.FAILED
        filing.error_message = str(e)
        db.commit()
        return False


async def get_filings_to_process(db: Session, status_filter=None, filing_type=None, limit=None):
    """获取需要处理的财报列表"""
    query = select(Filing).join(Company)
    
    # 状态过滤
    if status_filter:
        if isinstance(status_filter, list):
            query = query.filter(Filing.status.in_(status_filter))
        else:
            query = query.filter(Filing.status == status_filter)
    
    # 类型过滤
    if filing_type:
        query = query.filter(Filing.filing_type == filing_type)
    
    # 排序：优先处理最新的
    query = query.order_by(Filing.filing_date.desc())
    
    # 限制数量
    if limit:
        query = query.limit(limit)
    
    result = db.execute(query)
    return result.scalars().all()


async def show_statistics(db: Session):
    """显示当前统计信息"""
    # 总体统计
    total = db.query(Filing).count()
    completed = db.query(Filing).filter(Filing.status == ProcessingStatus.COMPLETED).count()
    failed = db.query(Filing).filter(Filing.status == ProcessingStatus.FAILED).count()
    pending = db.query(Filing).filter(Filing.status == ProcessingStatus.PENDING).count()
    
    print("\n📊 当前财报处理状态:")
    print(f"总数: {total}")
    print(f"✅ 已完成: {completed} ({completed/total*100:.1f}%)")
    print(f"❌ 失败: {failed} ({failed/total*100:.1f}%)")
    print(f"⏳ 待处理: {pending} ({pending/total*100:.1f}%)")
    
    # 按类型统计
    print("\n📈 按类型统计:")
    for filing_type in FilingType:
        type_total = db.query(Filing).filter(Filing.filing_type == filing_type).count()
        type_completed = db.query(Filing).filter(
            Filing.filing_type == filing_type,
            Filing.status == ProcessingStatus.COMPLETED
        ).count()
        if type_total > 0:
            print(f"{filing_type.value}: {type_completed}/{type_total} ({type_completed/type_total*100:.1f}%)")
    
    # 市场影响分析统计
    print("\n🎯 市场影响分析统计:")
    k10_with_impact = db.query(Filing).filter(
        Filing.filing_type == FilingType.FORM_10K,
        Filing.market_impact_10k.isnot(None)
    ).count()
    k10_total = db.query(Filing).filter(Filing.filing_type == FilingType.FORM_10K).count()
    
    q10_with_impact = db.query(Filing).filter(
        Filing.filing_type == FilingType.FORM_10Q,
        Filing.market_impact_10q.isnot(None)
    ).count()
    q10_total = db.query(Filing).filter(Filing.filing_type == FilingType.FORM_10Q).count()
    
    k10_percentage = k10_with_impact/k10_total*100 if k10_total > 0 else 0
    q10_percentage = q10_with_impact/q10_total*100 if q10_total > 0 else 0
    
    print(f"10-K 市场影响分析: {k10_with_impact}/{k10_total} ({k10_percentage:.1f}%)")
    print(f"10-Q 市场影响分析: {q10_with_impact}/{q10_total} ({q10_percentage:.1f}%)")


async def main():
    """主函数"""
    print("🚀 Fintellic 财报批量处理工具")
    print("=" * 50)
    
    db = SessionLocal()
    
    try:
        # 显示当前统计
        await show_statistics(db)
        
        # 询问处理选项
        print("\n请选择处理选项:")
        print("1. 处理所有失败的财报")
        print("2. 处理所有待处理的财报")
        print("3. 处理失败和待处理的财报")
        print("4. 只处理 10-K 财报")
        print("5. 只处理 10-Q 财报")
        print("6. 测试处理 5 个财报")
        print("0. 退出")
        
        choice = input("\n请输入选项 (0-6): ").strip()
        
        if choice == "0":
            print("退出程序")
            return
        
        # 确定要处理的财报
        filings_to_process = []
        
        if choice == "1":
            filings_to_process = await get_filings_to_process(db, ProcessingStatus.FAILED)
        elif choice == "2":
            filings_to_process = await get_filings_to_process(db, ProcessingStatus.PENDING)
        elif choice == "3":
            filings_to_process = await get_filings_to_process(db, [ProcessingStatus.FAILED, ProcessingStatus.PENDING])
        elif choice == "4":
            filings_to_process = await get_filings_to_process(
                db, 
                [ProcessingStatus.FAILED, ProcessingStatus.PENDING],
                FilingType.FORM_10K
            )
        elif choice == "5":
            filings_to_process = await get_filings_to_process(
                db, 
                [ProcessingStatus.FAILED, ProcessingStatus.PENDING],
                FilingType.FORM_10Q
            )
        elif choice == "6":
            filings_to_process = await get_filings_to_process(
                db, 
                [ProcessingStatus.FAILED, ProcessingStatus.PENDING],
                limit=5
            )
        else:
            print("无效选项")
            return
        
        if not filings_to_process:
            print("\n✅ 没有需要处理的财报!")
            return
        
        print(f"\n准备处理 {len(filings_to_process)} 个财报")
        confirm = input("是否继续? (y/n): ").strip().lower()
        
        if confirm != 'y':
            print("取消处理")
            return
        
        # 开始处理
        print(f"\n开始处理...")
        start_time = datetime.now()
        success_count = 0
        fail_count = 0
        
        for i, filing in enumerate(filings_to_process, 1):
            print(f"\n[{i}/{len(filings_to_process)}] 处理中...")
            success = await process_single_filing(db, filing)
            
            if success:
                success_count += 1
            else:
                fail_count += 1
            
            # 每处理 10 个暂停一下，避免 API 限流
            if i % 10 == 0:
                print("暂停 5 秒，避免 API 限流...")
                await asyncio.sleep(5)
        
        # 处理完成
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print("\n" + "=" * 50)
        print("✅ 批量处理完成!")
        print(f"成功: {success_count}")
        print(f"失败: {fail_count}")
        print(f"耗时: {duration:.1f} 秒")
        
        # 显示最终统计
        await show_statistics(db)
        
    except Exception as e:
        logger.error(f"程序出错: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python
"""
只处理那些已经成功下载文件的财报
"""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models.filing import Filing, ProcessingStatus, FilingType
from app.models.company import Company
from app.services.ai_processor import ai_processor
from app.core.database import engine
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def check_filing_has_files(filing):
    """检查财报是否有实际文件"""
    filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
    
    if not filing_dir.exists():
        return False, []
    
    # 获取实际文件（排除index.htm）
    files = [f for f in filing_dir.glob("*") if f.is_file() and f.name not in ['index.htm', 'index.html']]
    
    # 检查是否有文档文件
    doc_files = [f for f in files if f.suffix.lower() in ['.htm', '.html', '.xml', '.txt']]
    
    return len(doc_files) > 0, files


async def process_filings_with_files():
    """只处理有文件的财报"""
    db = SessionLocal()
    
    try:
        # 获取所有未完成的财报
        unprocessed_filings = db.query(Filing).join(Company).filter(
            Filing.status.in_([ProcessingStatus.FAILED, ProcessingStatus.PENDING, ProcessingStatus.PARSING])
        ).all()
        
        # 过滤出有文件的财报
        filings_with_files = []
        
        print("🔍 检查财报文件...")
        for filing in unprocessed_filings:
            # 跳过测试数据
            if filing.accession_number.startswith('TEST'):
                continue
                
            has_files, files = check_filing_has_files(filing)
            if has_files:
                filings_with_files.append({
                    'filing': filing,
                    'files': files
                })
        
        # 按类型统计
        type_stats = {}
        for item in filings_with_files:
            filing_type = item['filing'].filing_type.value
            if filing_type not in type_stats:
                type_stats[filing_type] = 0
            type_stats[filing_type] += 1
        
        print(f"\n📊 找到 {len(filings_with_files)} 个有文件的财报:")
        for filing_type, count in type_stats.items():
            print(f"{filing_type}: {count} 个")
        
        if not filings_with_files:
            print("\n❌ 没有找到有文件的未处理财报")
            return
        
        # 显示前10个
        print(f"\n📋 即将处理的财报（前10个）:")
        for i, item in enumerate(filings_with_files[:10], 1):
            filing = item['filing']
            files = item['files']
            print(f"{i}. {filing.company.ticker} - {filing.filing_type.value} - {filing.filing_date}")
            print(f"   文件: {[f.name for f in files[:3]]}")
        
        # 确认处理
        print(f"\n准备处理 {len(filings_with_files)} 个财报")
        confirm = input("是否继续? (y/n): ").strip().lower()
        
        if confirm != 'y':
            print("取消处理")
            return
        
        # 开始处理
        print(f"\n开始处理...")
        start_time = datetime.now()
        success_count = 0
        fail_count = 0
        
        # 按类型统计成功率
        success_by_type = {}
        
        for i, item in enumerate(filings_with_files, 1):
            filing = item['filing']
            print(f"\n[{i}/{len(filings_with_files)}] 处理 {filing.company.ticker} - {filing.filing_type.value}")
            
            try:
                success = await ai_processor.process_filing(db, filing)
                
                if success:
                    success_count += 1
                    filing_type = filing.filing_type.value
                    if filing_type not in success_by_type:
                        success_by_type[filing_type] = {'success': 0, 'total': 0}
                    success_by_type[filing_type]['success'] += 1
                    
                    # 检查是否生成了市场影响分析
                    if filing.filing_type == FilingType.FORM_10K and filing.market_impact_10k:
                        logger.info("  ✅ 已生成 10-K 市场影响分析")
                    elif filing.filing_type == FilingType.FORM_10Q and filing.market_impact_10q:
                        logger.info("  ✅ 已生成 10-Q 市场影响分析")
                else:
                    fail_count += 1
                    logger.error(f"  ❌ 处理失败: {filing.error_message}")
                
                # 更新类型统计
                filing_type = filing.filing_type.value
                if filing_type not in success_by_type:
                    success_by_type[filing_type] = {'success': 0, 'total': 0}
                success_by_type[filing_type]['total'] += 1
                
            except Exception as e:
                logger.error(f"处理出错: {str(e)}")
                fail_count += 1
            
            # 每处理10个暂停一下
            if i % 10 == 0 and i < len(filings_with_files):
                print("暂停5秒，避免API限流...")
                await asyncio.sleep(5)
        
        # 显示结果
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n{'='*60}")
        print(f"✅ 处理完成!")
        print(f"成功: {success_count}")
        print(f"失败: {fail_count}")
        print(f"总耗时: {elapsed:.1f} 秒")
        
        # 按类型显示成功率
        print(f"\n📈 按类型成功率:")
        for filing_type, stats in success_by_type.items():
            success_rate = stats['success'] / stats['total'] * 100 if stats['total'] > 0 else 0
            print(f"{filing_type}: {stats['success']}/{stats['total']} ({success_rate:.1f}%)")
        
        # 显示最终统计
        print(f"\n📊 最终财报状态:")
        total = db.query(Filing).count()
        completed = db.query(Filing).filter(Filing.status == ProcessingStatus.COMPLETED).count()
        failed = db.query(Filing).filter(Filing.status == ProcessingStatus.FAILED).count()
        pending = db.query(Filing).filter(Filing.status == ProcessingStatus.PENDING).count()
        
        print(f"总数: {total}")
        print(f"✅ 已完成: {completed} ({completed/total*100:.1f}%)")
        print(f"❌ 失败: {failed} ({failed/total*100:.1f}%)")
        print(f"⏳ 待处理: {pending} ({pending/total*100:.1f}%)")
        
        # 市场影响分析统计
        print(f"\n🎯 市场影响分析统计:")
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
        
    except Exception as e:
        logger.error(f"程序出错: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print("🚀 处理已有文件的财报")
    print("=" * 60)
    
    asyncio.run(process_filings_with_files())
#!/usr/bin/env python
"""
使用现有的 filing_downloader 服务重新下载缺失的财报文件
"""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
import logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.filing import Filing, ProcessingStatus
from app.models.company import Company
from app.core.database import engine
from app.services.filing_downloader import filing_downloader  # 使用现有的下载服务

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def check_filing_has_files(filing):
    """检查财报是否有文件"""
    filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
    
    if not filing_dir.exists():
        return False, "no_directory"
    
    files = list(filing_dir.glob("*"))
    # 排除 index.htm
    files = [f for f in files if f.name not in ['index.htm', 'index.html']]
    
    if not files:
        return False, "empty_directory"
    
    # 检查是否有主要文档
    doc_files = [f for f in files if f.suffix.lower() in ['.htm', '.html', '.xml', '.txt']]
    if not doc_files:
        return False, "no_documents"
    
    return True, f"{len(files)}_files"


async def download_single_filing(db, filing):
    """下载单个财报"""
    try:
        logger.info(f"开始下载: {filing.company.ticker} - {filing.filing_type.value} - {filing.accession_number}")
        
        # 重置状态为 PENDING，让 filing_downloader 处理
        filing.status = ProcessingStatus.PENDING
        filing.error_message = None
        db.commit()
        
        # 使用现有的 filing_downloader 服务
        success = await filing_downloader.download_filing(db, filing)
        
        if success:
            # 验证文件
            has_files, status = check_filing_has_files(filing)
            if has_files:
                logger.info(f"✅ 下载成功: {filing.accession_number} ({status})")
                return True
            else:
                logger.error(f"下载后仍无文件: {status}")
                filing.status = ProcessingStatus.FAILED
                filing.error_message = f"Download completed but no files found: {status}"
                db.commit()
                return False
        else:
            logger.error(f"下载失败: {filing.accession_number}")
            return False
            
    except Exception as e:
        logger.error(f"下载出错 {filing.accession_number}: {str(e)}")
        filing.status = ProcessingStatus.FAILED
        filing.error_message = str(e)
        db.commit()
        return False


async def main():
    """主函数"""
    db = SessionLocal()
    
    try:
        # 首先测试连接
        logger.info("测试 SEC EDGAR 连接...")
        can_connect = await filing_downloader.test_connection()
        if not can_connect:
            logger.error("无法连接到 SEC EDGAR，请检查网络")
            return
        
        # 获取所有财报
        all_filings = db.query(Filing).join(Company).all()
        
        # 分析文件状态
        print("\n🔍 分析财报文件状态...")
        
        filings_to_download = []
        filings_with_files = []
        test_filings = []
        
        for filing in all_filings:
            # 跳过测试数据
            if filing.accession_number.startswith('TEST'):
                test_filings.append(filing)
                continue
                
            has_files, status = check_filing_has_files(filing)
            
            if has_files:
                filings_with_files.append(filing)
            else:
                filings_to_download.append({
                    'filing': filing,
                    'status': status
                })
        
        # 显示统计
        print(f"\n📊 文件状态统计:")
        print(f"总财报数: {len(all_filings)}")
        print(f"✅ 已有文件: {len(filings_with_files)} ({len(filings_with_files)/len(all_filings)*100:.1f}%)")
        print(f"❌ 需要下载: {len(filings_to_download)} ({len(filings_to_download)/len(all_filings)*100:.1f}%)")
        print(f"🧪 测试数据: {len(test_filings)}")
        
        if not filings_to_download:
            print("\n✅ 所有财报都已有文件!")
            return
        
        # 按状态分组
        status_groups = {}
        for item in filings_to_download:
            status = item['status']
            if status not in status_groups:
                status_groups[status] = []
            status_groups[status].append(item['filing'])
        
        print(f"\n📈 缺失文件的原因:")
        for status, filings in status_groups.items():
            print(f"{status}: {len(filings)} 个")
        
        # 显示前5个缺失文件的财报
        print(f"\n🔍 即将下载的财报 (前5个):")
        for i, item in enumerate(filings_to_download[:5], 1):
            filing = item['filing']
            print(f"{i}. {filing.company.ticker} - {filing.filing_type.value} - {filing.filing_date}")
        
        # 确认下载
        print(f"\n准备下载 {len(filings_to_download)} 个财报")
        confirm = input("是否继续? (y/n/test): ").strip().lower()
        
        if confirm == 'test':
            # 只下载前5个测试
            filings_to_download = filings_to_download[:5]
            print("测试模式：只下载前5个")
        elif confirm != 'y':
            print("取消下载")
            return
        
        # 开始下载
        print(f"\n开始下载...")
        start_time = datetime.now()
        success_count = 0
        fail_count = 0
        failed_filings = []
        
        for i, item in enumerate(filings_to_download, 1):
            filing = item['filing']
            print(f"\n[{i}/{len(filings_to_download)}] {filing.company.ticker} - {filing.filing_type.value}")
            
            success = await download_single_filing(db, filing)
            
            if success:
                success_count += 1
            else:
                fail_count += 1
                failed_filings.append(filing)
            
            # 避免过快请求
            if i < len(filings_to_download):  # 最后一个不需要等待
                await asyncio.sleep(0.5)  # SEC 限制
        
        # 显示结果
        elapsed_total = (datetime.now() - start_time).total_seconds()
        print(f"\n{'='*60}")
        print(f"✅ 下载完成!")
        print(f"成功: {success_count}")
        print(f"失败: {fail_count}")
        print(f"总耗时: {elapsed_total:.1f} 秒")
        
        if failed_filings:
            print(f"\n❌ 下载失败的财报:")
            for filing in failed_filings[:10]:
                print(f"- {filing.company.ticker} - {filing.filing_type.value} - {filing.accession_number}")
                if filing.error_message:
                    print(f"  错误: {filing.error_message}")
        
    except Exception as e:
        logger.error(f"程序出错: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print("📥 Fintellic 财报文件下载工具")
    print("=" * 60)
    print("使用现有的 filing_downloader 服务")
    print("=" * 60)
    
    asyncio.run(main())
#!/usr/bin/env python
"""
下载缺失的财报文件
"""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.filing import Filing, ProcessingStatus
from app.models.company import Company
from app.core.database import engine
from app.services.sec_downloader import sec_downloader
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


async def download_filing_files(db, filing):
    """下载单个财报的文件"""
    try:
        # 构建文件路径
        filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
        
        # 检查是否已存在文件
        if filing_dir.exists():
            files = list(filing_dir.glob("*"))
            if files:
                logger.info(f"文件已存在: {filing.company.ticker} - {filing.filing_type.value}")
                return True
        
        logger.info(f"开始下载: {filing.company.ticker} - {filing.filing_type.value} - {filing.accession_number}")
        
        # 使用 sec_downloader 下载文件
        success = await sec_downloader.download_filing(
            cik=filing.company.cik,
            accession_number=filing.accession_number,
            company_ticker=filing.company.ticker,
            filing_type=filing.filing_type.value
        )
        
        if success:
            logger.info(f"✅ 下载成功: {filing.accession_number}")
            # 更新状态为待处理
            filing.status = ProcessingStatus.PENDING
            filing.error_message = None
            db.commit()
        else:
            logger.error(f"❌ 下载失败: {filing.accession_number}")
            
        return success
        
    except Exception as e:
        logger.error(f"下载出错 {filing.accession_number}: {str(e)}")
        return False


async def download_missing_files():
    """下载所有缺失文件的财报"""
    db = SessionLocal()
    
    try:
        # 获取所有失败或待处理的财报
        filings = db.query(Filing).join(Company).filter(
            Filing.status.in_([ProcessingStatus.FAILED, ProcessingStatus.PENDING])
        ).all()
        
        print(f"\n📥 准备下载 {len(filings)} 个财报的文件")
        
        # 询问确认
        confirm = input("是否继续? (y/n): ").strip().lower()
        if confirm != 'y':
            print("取消下载")
            return
        
        # 开始下载
        success_count = 0
        fail_count = 0
        
        for i, filing in enumerate(filings, 1):
            print(f"\n[{i}/{len(filings)}] 下载中...")
            
            # 检查是否需要下载
            filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
            if filing_dir.exists() and list(filing_dir.glob("*")):
                print(f"跳过 - 文件已存在: {filing.company.ticker}")
                continue
            
            success = await download_filing_files(db, filing)
            
            if success:
                success_count += 1
            else:
                fail_count += 1
            
            # 避免请求过快
            await asyncio.sleep(1)
            
            # 每下载10个休息一下
            if i % 10 == 0:
                print("暂停5秒...")
                await asyncio.sleep(5)
        
        print(f"\n下载完成!")
        print(f"成功: {success_count}")
        print(f"失败: {fail_count}")
        
    except Exception as e:
        logger.error(f"下载过程出错: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


async def test_single_download():
    """测试下载单个财报"""
    db = SessionLocal()
    
    try:
        # 获取一个失败的财报
        filing = db.query(Filing).join(Company).filter(
            Filing.status == ProcessingStatus.FAILED
        ).first()
        
        if filing:
            print(f"\n测试下载: {filing.company.ticker} - {filing.filing_type.value}")
            print(f"CIK: {filing.company.cik}")
            print(f"Accession: {filing.accession_number}")
            
            success = await download_filing_files(db, filing)
            
            if success:
                print("✅ 测试下载成功!")
                
                # 检查文件
                filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
                if filing_dir.exists():
                    files = list(filing_dir.glob("*"))
                    print(f"下载的文件: {len(files)} 个")
                    for f in files[:5]:
                        print(f"  - {f.name}")
            else:
                print("❌ 测试下载失败")
        else:
            print("没有找到失败的财报")
            
    finally:
        db.close()


if __name__ == "__main__":
    print("📥 Fintellic 财报文件下载工具")
    print("=" * 50)
    
    print("选择操作:")
    print("1. 测试下载单个财报")
    print("2. 下载所有缺失的文件")
    
    choice = input("\n请选择 (1-2): ").strip()
    
    if choice == "1":
        asyncio.run(test_single_download())
    elif choice == "2":
        asyncio.run(download_missing_files())
    else:
        print("无效选择")
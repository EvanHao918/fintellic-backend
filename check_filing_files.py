#!/usr/bin/env python
"""
检查财报文件系统状态
"""
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models.filing import Filing, ProcessingStatus
from app.models.company import Company
from app.core.database import engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def check_filing_files():
    """检查财报文件系统"""
    db = SessionLocal()
    
    # 获取所有财报
    filings = db.query(Filing).join(Company).all()
    
    print(f"📁 检查财报文件系统")
    print("=" * 60)
    
    # 统计
    total = len(filings)
    with_files = 0
    without_files = 0
    empty_dirs = 0
    
    # 详细检查
    missing_files_list = []
    
    for filing in filings:
        # 构建文件路径
        filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
        
        if filing_dir.exists():
            # 检查目录中的文件
            files = list(filing_dir.glob("*"))
            if files:
                with_files += 1
            else:
                empty_dirs += 1
                missing_files_list.append({
                    'ticker': filing.company.ticker,
                    'type': filing.filing_type.value,
                    'date': filing.filing_date,
                    'path': str(filing_dir),
                    'status': filing.status.value
                })
        else:
            without_files += 1
            missing_files_list.append({
                'ticker': filing.company.ticker,
                'type': filing.filing_type.value,
                'date': filing.filing_date,
                'path': str(filing_dir),
                'status': filing.status.value
            })
    
    # 打印统计
    print(f"总财报数: {total}")
    print(f"✅ 有文件的: {with_files} ({with_files/total*100:.1f}%)")
    print(f"📂 空目录: {empty_dirs} ({empty_dirs/total*100:.1f}%)")
    print(f"❌ 无目录: {without_files} ({without_files/total*100:.1f}%)")
    
    # 显示前10个缺失文件的财报
    print(f"\n🔍 缺失文件的财报 (前10个):")
    print("-" * 60)
    for i, filing in enumerate(missing_files_list[:10], 1):
        print(f"{i}. {filing['ticker']} - {filing['type']} - {filing['date']}")
        print(f"   路径: {filing['path']}")
        print(f"   状态: {filing['status']}")
    
    # 检查data目录结构
    print(f"\n📊 文件系统结构:")
    data_dir = Path("data/filings")
    if data_dir.exists():
        # 统计CIK目录数
        cik_dirs = list(data_dir.iterdir())
        print(f"CIK目录数: {len(cik_dirs)}")
        
        # 统计总文件数
        total_files = 0
        for cik_dir in cik_dirs:
            if cik_dir.is_dir():
                for filing_dir in cik_dir.iterdir():
                    if filing_dir.is_dir():
                        files = list(filing_dir.glob("*"))
                        total_files += len(files)
        
        print(f"总文件数: {total_files}")
    else:
        print("❌ data/filings 目录不存在!")
    
    db.close()
    
    return missing_files_list


def check_sample_filing_detail():
    """详细检查一个样本财报"""
    db = SessionLocal()
    
    # 获取一个失败的财报
    sample = db.query(Filing).filter(Filing.status == ProcessingStatus.FAILED).first()
    
    if sample:
        print(f"\n🔬 详细检查样本财报:")
        print(f"公司: {sample.company.ticker}")
        print(f"类型: {sample.filing_type.value}")
        print(f"CIK: {sample.company.cik}")
        print(f"Accession: {sample.accession_number}")
        
        # 检查各种可能的路径
        possible_paths = [
            f"data/filings/{sample.company.cik}/{sample.accession_number.replace('-', '')}",
            f"data/filings/{sample.company.cik}/{sample.accession_number}",
            f"filings/{sample.company.cik}/{sample.accession_number.replace('-', '')}",
            f"filings/{sample.company.cik}/{sample.accession_number}",
        ]
        
        print("\n检查可能的路径:")
        for path in possible_paths:
            p = Path(path)
            if p.exists():
                files = list(p.glob("*"))
                print(f"✅ {path} - 存在 ({len(files)} 个文件)")
                if files:
                    print(f"   文件: {[f.name for f in files[:5]]}")
            else:
                print(f"❌ {path} - 不存在")
    
    db.close()


if __name__ == "__main__":
    print("🔍 Fintellic 财报文件系统检查")
    print("=" * 60)
    
    # 检查文件系统
    missing_list = check_filing_files()
    
    # 检查样本
    check_sample_filing_detail()
    
    # 建议
    print("\n💡 建议:")
    if len(missing_list) > 0:
        print("1. 大部分财报文件缺失，需要重新下载")
        print("2. 可能需要运行文件下载脚本")
        print("3. 检查 SEC_DOWNLOADER 服务是否正常工作")
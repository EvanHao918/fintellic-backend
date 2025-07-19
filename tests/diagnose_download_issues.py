#!/usr/bin/env python3
"""
诊断财报下载问题
检查为什么下载的是HTML文件而不是真正的财报
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import Filing
from pathlib import Path
import requests
from bs4 import BeautifulSoup

def diagnose_download_issues():
    db = next(get_db())
    
    print("=" * 80)
    print("财报下载问题诊断")
    print("=" * 80)
    
    # 1. 检查最近的失败案例
    print("\n1. 检查失败的财报:")
    failed_filings = db.query(Filing).filter(
        Filing.status.in_(['FAILED', 'DOWNLOADED'])
    ).limit(5).all()
    
    for f in failed_filings:
        print(f"\n  {f.company.ticker} - {f.filing_type} (ID: {f.id})")
        print(f"  - 状态: {f.status}")
        print(f"  - URL: {f.file_url if hasattr(f, 'file_url') else 'N/A'}")
        if hasattr(f, 'accession_number'):
            print(f"  - Accession: {f.accession_number}")
    
    # 2. 检查实际下载的文件
    print("\n\n2. 检查已下载文件的内容:")
    data_dir = Path("data/filings")
    
    # 找几个实际存在的文件
    sample_files = []
    for cik_dir in data_dir.glob("*"):
        if cik_dir.is_dir():
            for acc_dir in cik_dir.glob("*"):
                if acc_dir.is_dir():
                    files = list(acc_dir.glob("*.htm*"))
                    if files:
                        sample_files.append(files[0])
                        if len(sample_files) >= 3:
                            break
            if len(sample_files) >= 3:
                break
    
    for file_path in sample_files:
        print(f"\n  文件: {file_path.relative_to(data_dir)}")
        print(f"  大小: {file_path.stat().st_size / 1024:.1f} KB")
        
        # 读取文件内容的前1000个字符
        try:
            content = file_path.read_text(errors='ignore')[:1000]
            
            # 检查是否是真正的财报
            if "DOCTYPE html" in content and len(content) < 5000:
                print("  ❌ 可能是索引页或错误页")
            elif "10-K" in content or "10-Q" in content or "Part I" in content:
                print("  ✅ 看起来是真正的财报")
            else:
                print("  ⚠️  内容不确定")
            
            # 显示一些内容
            soup = BeautifulSoup(content, 'html.parser')
            text = soup.get_text().strip()[:200]
            print(f"  内容预览: {text}...")
            
        except Exception as e:
            print(f"  ❌ 读取错误: {e}")
    
    # 3. 测试SEC URL格式
    print("\n\n3. 测试SEC URL格式:")
    
    # 以UAL为例
    ual_filing = db.query(Filing).filter(Filing.id == 90).first()
    if ual_filing and hasattr(ual_filing, 'accession_number'):
        cik = ual_filing.company.cik.lstrip('0')
        acc_no = ual_filing.accession_number.replace('-', '')
        
        test_urls = [
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no}/{acc_no}.txt",
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no}/index.htm",
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no}/form10-q.htm",
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no}/ual-10q.htm",
        ]
        
        print(f"  测试UAL财报URL (CIK: {cik}, Accession: {ual_filing.accession_number}):")
        
        for url in test_urls:
            try:
                response = requests.head(url, timeout=5)
                print(f"  - {url}")
                print(f"    状态: {response.status_code}")
            except Exception as e:
                print(f"  - {url}")
                print(f"    错误: {e}")
    
    # 4. 建议
    print("\n\n4. 问题分析与建议:")
    print("=" * 80)
    print("常见问题:")
    print("1. 下载的是index.htm而不是真正的财报文件")
    print("2. SEC的URL格式经常变化")
    print("3. 需要从index.htm中解析出真正的财报文件链接")
    print("\n建议解决方案:")
    print("1. 先下载index.htm")
    print("2. 解析index.htm找到主文档链接（通常是最大的.htm文件）")
    print("3. 下载真正的财报文件")
    print("4. 验证文件大小（真正的10-K/10-Q通常>100KB）")


if __name__ == "__main__":
    diagnose_download_issues()
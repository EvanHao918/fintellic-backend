#!/usr/bin/env python3
"""
诊断SEC财报URL格式
找出正确的URL模式
"""

import httpx
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
import asyncio
import time


async def test_url(url: str) -> tuple[bool, int]:
    """测试URL是否有效"""
    headers = {
        'User-Agent': 'Fintellic/1.0 (contact@fintellic.com)'
    }
    
    try:
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            response = await client.head(url)
            return response.status_code == 200, response.status_code
    except Exception as e:
        return False, 0


async def diagnose_filing_urls():
    """诊断失败财报的正确URL格式"""
    db = SessionLocal()
    
    # 获取几个失败的财报
    failed_filings = db.query(Filing).filter(
        Filing.status == ProcessingStatus.FAILED
    ).limit(3).all()
    
    print("=" * 80)
    print("SEC财报URL诊断")
    print("=" * 80)
    
    for filing in failed_filings:
        print(f"\n检查: {filing.company.ticker} {filing.filing_type.value}")
        print(f"CIK: {filing.company.cik}")
        print(f"Accession: {filing.accession_number}")
        print("-" * 40)
        
        # 准备各种可能的URL格式
        cik = filing.company.cik
        acc_no = filing.accession_number
        
        # 测试不同的CIK格式
        cik_formats = [
            cik,  # 原始
            cik.lstrip('0'),  # 去掉前导0
            cik.zfill(10),  # 填充到10位
            cik.zfill(7),  # 填充到7位
        ]
        
        # 测试不同的accession格式
        acc_formats = [
            acc_no,  # 原始 (带横线)
            acc_no.replace('-', ''),  # 去掉横线
        ]
        
        # 测试不同的文件名
        filenames = [
            '-index.htm',
            'index.htm',
            '-index.html',
            'index.html',
            f'{acc_no}-index.htm',
            f'{acc_no.replace("-", "")}-index.htm',
        ]
        
        found = False
        
        for cik_fmt in cik_formats:
            if found:
                break
                
            for acc_fmt in acc_formats:
                if found:
                    break
                    
                for filename in filenames:
                    url = f"https://www.sec.gov/Archives/edgar/data/{cik_fmt}/{acc_fmt}/{filename}"
                    
                    # 限速
                    time.sleep(0.1)
                    
                    success, status = await test_url(url)
                    
                    if success:
                        print(f"✅ 找到了! URL格式:")
                        print(f"   CIK格式: {cik_fmt} (原始: {cik})")
                        print(f"   Accession格式: {acc_fmt} (原始: {acc_no})")
                        print(f"   文件名: {filename}")
                        print(f"   完整URL: {url}")
                        found = True
                        break
                    elif status == 403:
                        print(f"⚠️  403 Forbidden - 可能需要调整User-Agent")
                    elif status == 404:
                        # 404很常见，不打印
                        pass
                    else:
                        print(f"❌ {url} -> {status}")
        
        if not found:
            print("❌ 无法找到正确的URL格式")
            
            # 尝试获取该公司的其他财报看看格式
            other_filing = db.query(Filing).filter(
                Filing.company_id == filing.company_id,
                Filing.status == ProcessingStatus.COMPLETED
            ).first()
            
            if other_filing and other_filing.primary_doc_url:
                print(f"\n参考: 该公司其他成功的财报URL:")
                print(f"   {other_filing.primary_doc_url}")
    
    db.close()


async def test_known_good_url():
    """测试一个已知的好URL来验证连接"""
    print("\n" + "=" * 40)
    print("测试已知的SEC URL...")
    
    # Apple的一个已知财报
    test_url_str = "https://www.sec.gov/Archives/edgar/data/0000320193/000032019324000123/-index.htm"
    success, status = await test_url(test_url_str)
    
    if success:
        print(f"✅ 连接正常: {test_url_str}")
    else:
        print(f"❌ 连接失败 ({status}): {test_url_str}")
        print("可能是网络问题或需要代理")


if __name__ == "__main__":
    print("开始诊断SEC URL格式...\n")
    asyncio.run(test_known_good_url())
    asyncio.run(diagnose_filing_urls())
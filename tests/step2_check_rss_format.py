#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import asyncio
from app.services.sec_client import SECClient

async def check_rss():
    print("=== STEP 2: 检查 RSS Feed 数据格式 ===\n")
    
    sec_client = SECClient()
    
    # 获取最近2小时的财报
    print("获取最近的 RSS 数据...")
    filings = await sec_client.get_rss_filings("all", lookback_minutes=120)
    
    if not filings:
        print("❌ 没有获取到任何财报数据")
        return
    
    print(f"\n✅ 获取到 {len(filings)} 个财报\n")
    
    # 检查前10个财报的CIK格式
    print("RSS 中的 CIK 格式样本:")
    for i, filing in enumerate(filings[:10]):
        cik = filing.get('cik', 'N/A')
        print(f"{i+1}. {filing['form']} - {filing['company_name'][:30]}...")
        print(f"   CIK: '{cik}' (长度={len(cik) if cik != 'N/A' else 0})")
        print(f"   日期: {filing['filing_date']}")
    
    # 统计CIK长度分布
    print("\nCIK 长度分布:")
    length_dist = {}
    for filing in filings:
        cik = filing.get('cik', '')
        length = len(cik)
        length_dist[length] = length_dist.get(length, 0) + 1
    
    for length, count in sorted(length_dist.items()):
        print(f"  长度 {length}: {count} 个")

if __name__ == "__main__":
    asyncio.run(check_rss())

#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import asyncio
from app.core.database import SessionLocal
from app.models import Company
from app.services.sec_client import SECClient

async def check_matching():
    print("=== STEP 3: 检查 RSS 财报与监控公司的匹配 ===\n")
    
    db = SessionLocal()
    sec_client = SECClient()
    
    try:
        # 1. 获取所有监控的 CIK
        monitored_companies = db.query(Company).filter(
            (Company.is_sp500 == True) | (Company.is_nasdaq100 == True)
        ).all()
        
        monitored_ciks = {company.cik for company in monitored_companies}
        print(f"监控 CIK 数量: {len(monitored_ciks)}")
        
        # 2. 获取最近的 RSS 数据
        filings = await sec_client.get_rss_filings("all", lookback_minutes=120)
        print(f"RSS 财报数量: {len(filings)}\n")
        
        # 3. 检查每个财报
        print("检查 RSS 中的公司:")
        matched = 0
        
        for filing in filings:
            rss_cik = filing['cik']
            
            # 检查是否在监控列表中
            if rss_cik in monitored_ciks:
                # 找到匹配！
                company = db.query(Company).filter(Company.cik == rss_cik).first()
                print(f"\n✅ 匹配: {company.ticker} - {company.name}")
                print(f"   财报: {filing['form']} 日期: {filing['filing_date']}")
                print(f"   指数: S&P500={company.is_sp500}, NASDAQ100={company.is_nasdaq100}")
                matched += 1
            else:
                # 不在监控列表中，查看是什么公司
                company = db.query(Company).filter(Company.cik == rss_cik).first()
                if company:
                    print(f"\n❌ 不在监控列表: {company.ticker} - {company.name}")
                    print(f"   S&P500={company.is_sp500}, NASDAQ100={company.is_nasdaq100}")
                else:
                    print(f"\n❌ 未知公司: {filing['company_name'][:50]}... (CIK: {rss_cik})")
        
        print(f"\n总结: {matched}/{len(filings)} 个财报来自监控的公司")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(check_matching())

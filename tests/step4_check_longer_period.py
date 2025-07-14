#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import asyncio
from app.core.database import SessionLocal
from app.models import Company, Filing
from app.services.sec_client import SECClient
from datetime import datetime, timedelta
from sqlalchemy import desc

async def check_longer_period():
    print("=== STEP 4: 检查更长时间范围和历史数据 ===\n")
    
    db = SessionLocal()
    sec_client = SECClient()
    
    try:
        # 1. 检查数据库中已有的财报
        total_filings = db.query(Filing).count()
        recent_filings = db.query(Filing).filter(
            Filing.filing_date >= datetime.now() - timedelta(days=7)
        ).count()
        
        print(f"数据库中的财报总数: {total_filings}")
        print(f"最近7天的财报数: {recent_filings}")
        
        # 获取最新的10个财报
        latest_filings = db.query(Filing).order_by(desc(Filing.filing_date)).limit(10).all()
        
        if latest_filings:
            print("\n数据库中最新的财报:")
            for f in latest_filings[:5]:
                print(f"- {f.company.ticker}: {f.filing_type.value} ({f.filing_date})")
        
        # 2. 检查RSS更长时间范围（6小时）
        print("\n\n获取最近6小时的RSS数据...")
        filings = await sec_client.get_rss_filings("all", lookback_minutes=360)
        
        if filings:
            print(f"RSS中找到 {len(filings)} 个财报")
            
            # 获取监控的CIK
            monitored_companies = db.query(Company).filter(
                (Company.is_sp500 == True) | (Company.is_nasdaq100 == True)
            ).all()
            monitored_ciks = {company.cik for company in monitored_companies}
            
            # 统计匹配情况
            matched = 0
            matched_companies = []
            
            for filing in filings:
                if filing['cik'] in monitored_ciks:
                    matched += 1
                    company = db.query(Company).filter(Company.cik == filing['cik']).first()
                    if company and len(matched_companies) < 10:  # 只显示前10个
                        matched_companies.append({
                            'ticker': company.ticker,
                            'name': company.name,
                            'form': filing['form'],
                            'date': filing['filing_date']
                        })
            
            print(f"\n6小时内的匹配情况: {matched}/{len(filings)} 个财报来自监控的公司")
            
            if matched_companies:
                print("\n匹配的公司财报:")
                for mc in matched_companies:
                    print(f"- {mc['ticker']}: {mc['form']} ({mc['date']})")
        
        # 3. 检查今天是周末还是工作日
        today = datetime.now()
        day_name = today.strftime("%A")
        print(f"\n\n今天是: {day_name}")
        if day_name in ['Saturday', 'Sunday']:
            print("📅 注意：今天是周末，通常财报提交较少")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(check_longer_period())

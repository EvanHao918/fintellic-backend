#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from app.core.database import SessionLocal
from app.models import Company

print("=== STEP 1: 检查数据库中的公司数据 ===\n")

db = SessionLocal()

try:
    # 1. 检查总数
    total_companies = db.query(Company).count()
    sp500_count = db.query(Company).filter(Company.is_sp500 == True).count()
    nasdaq100_count = db.query(Company).filter(Company.is_nasdaq100 == True).count()
    
    print(f"数据库中的公司总数: {total_companies}")
    print(f"S&P 500 公司数量: {sp500_count}")
    print(f"NASDAQ 100 公司数量: {nasdaq100_count}")
    
    # 2. 检查一些知名公司是否存在
    print("\n检查知名公司:")
    test_companies = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
    
    for ticker in test_companies:
        company = db.query(Company).filter(Company.ticker == ticker).first()
        if company:
            print(f"✅ {ticker}: CIK='{company.cik}' (长度={len(company.cik)}), S&P500={company.is_sp500}")
        else:
            print(f"❌ {ticker}: 未找到")
    
    # 3. 查看CIK格式样本
    print("\nCIK格式样本 (前10个S&P 500公司):")
    sample = db.query(Company).filter(Company.is_sp500 == True).limit(10).all()
    for company in sample:
        print(f"{company.ticker}: CIK='{company.cik}' (长度={len(company.cik)})")
        
except Exception as e:
    print(f"错误: {e}")
finally:
    db.close()

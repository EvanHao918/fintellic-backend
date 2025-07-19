#!/usr/bin/env python3
"""
诊断前端显示相同财务数据的问题
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import Filing, Company
import json

def diagnose_display_issue():
    """诊断前端显示问题"""
    db = next(get_db())
    
    print("=" * 80)
    print("Fintellic 前端显示问题诊断")
    print("=" * 80)
    
    # 1. 检查UAL和TRV的财报数据
    print("\n1. 检查UAL和TRV的财报数据:")
    
    # UAL财报 (ID: 90)
    ual_filing = db.query(Filing).filter(Filing.id == 90).first()
    if ual_filing:
        print(f"\nUAL财报 (ID: 90):")
        print(f"  - 公司: {ual_filing.company.ticker}")
        print(f"  - 类型: {ual_filing.filing_type}")
        print(f"  - AI摘要前50字: {ual_filing.ai_summary[:50] if ual_filing.ai_summary else 'None'}...")
        
        # 检查financial_highlights字段
        if hasattr(ual_filing, 'financial_highlights') and ual_filing.financial_highlights:
            print(f"  - financial_highlights: {json.dumps(ual_filing.financial_highlights, indent=2)}")
        else:
            print(f"  - financial_highlights: None")
            
        # 检查specific_data字段
        if hasattr(ual_filing, 'specific_data') and ual_filing.specific_data:
            print(f"  - specific_data: {json.dumps(ual_filing.specific_data, indent=2)}")
        else:
            print(f"  - specific_data: None")
    
    # TRV财报 (ID: 83)
    trv_filing = db.query(Filing).filter(Filing.id == 83).first()
    if trv_filing:
        print(f"\nTRV财报 (ID: 83):")
        print(f"  - 公司: {trv_filing.company.ticker}")
        print(f"  - 类型: {trv_filing.filing_type}")
        print(f"  - AI摘要前50字: {trv_filing.ai_summary[:50] if trv_filing.ai_summary else 'None'}...")
        
        # 检查financial_highlights字段
        if hasattr(trv_filing, 'financial_highlights') and trv_filing.financial_highlights:
            print(f"  - financial_highlights: {json.dumps(trv_filing.financial_highlights, indent=2)}")
        else:
            print(f"  - financial_highlights: None")
            
        # 检查specific_data字段
        if hasattr(trv_filing, 'specific_data') and trv_filing.specific_data:
            print(f"  - specific_data: {json.dumps(trv_filing.specific_data, indent=2)}")
        else:
            print(f"  - specific_data: None")
    
    # 2. 检查数据库中是否有硬编码的值
    print("\n\n2. 搜索数据库中包含 '13.7B' 的财报:")
    filings_with_137b = db.query(Filing).filter(
        Filing.ai_summary.contains('13.7B') | 
        Filing.ai_summary.contains('13.7 billion')
    ).all()
    
    if filings_with_137b:
        print(f"找到 {len(filings_with_137b)} 个包含 '13.7B' 的财报:")
        for f in filings_with_137b[:5]:  # 只显示前5个
            print(f"  - ID: {f.id}, 公司: {f.company.ticker}, 类型: {f.filing_type}")
    
    # 3. 检查是否有财报包含 "cloud services" 
    print("\n3. 搜索包含 'cloud services' 的财报:")
    cloud_filings = db.query(Filing).filter(
        Filing.ai_summary.contains('cloud services') | 
        Filing.ai_summary.contains('Cloud Services')
    ).all()
    
    if cloud_filings:
        print(f"找到 {len(cloud_filings)} 个包含 'cloud services' 的财报:")
        for f in cloud_filings[:5]:
            # Company模型可能没有industry字段
            industry = getattr(f.company, 'industry', 'N/A') if hasattr(f.company, 'industry') else 'N/A'
            print(f"  - ID: {f.id}, 公司: {f.company.ticker}, 类型: {f.filing_type}")
    
    # 4. 检查新的差异化字段
    print("\n\n4. 检查差异化显示字段 (Day 19-20新增):")
    
    # 检查10-Q财报的新字段
    tenq_filings = db.query(Filing).filter(Filing.filing_type == '10-Q').limit(3).all()
    for f in tenq_filings:
        print(f"\n10-Q财报 (ID: {f.id}, {f.company.ticker}):")
        
        # 检查新字段
        fields_to_check = [
            'quarterly_revenue', 'quarterly_earnings', 'yoy_comparison',
            'sequential_changes', 'guidance_updates', 'analyst_consensus',
            'earnings_surprise', 'operational_kpis', 'management_commentary',
            'market_impact_10q'
        ]
        
        for field in fields_to_check:
            if hasattr(f, field):
                value = getattr(f, field)
                if value:
                    print(f"  - {field}: {str(value)[:100]}...")
                else:
                    print(f"  - {field}: None")
    
    # 5. 提供解决建议
    print("\n\n5. 问题分析与解决建议:")
    print("=" * 80)
    
    if not (ual_filing and hasattr(ual_filing, 'financial_highlights') and ual_filing.financial_highlights):
        print("❌ 问题1: 财报缺少 financial_highlights 数据")
        print("   解决方案: 需要在后端AI处理器中添加财务数据提取逻辑")
        print("   文件位置: app/services/openai_processor.py")
    
    print("\n❌ 问题2: 前端可能使用了硬编码的示例数据")
    print("   检查位置: ")
    print("   - src/screens/FilingDetailScreen.tsx")
    print("   - generateVisualsForFiling 函数")
    print("   - 查找是否有硬编码的 '13.7B', '1.93', '28%' 等值")
    
    print("\n建议的修复步骤:")
    print("1. 后端: 确保AI处理器提取并存储 financial_highlights")
    print("2. 前端: 移除任何硬编码的财务数据")
    print("3. 前端: 使用后端返回的真实数据")
    print("4. 清理缓存: redis-cli FLUSHALL")

if __name__ == "__main__":
    diagnose_display_issue()
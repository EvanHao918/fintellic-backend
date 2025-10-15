#!/usr/bin/env python3
"""
简化版UAL财报诊断
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import Filing
import json
from pathlib import Path

def diagnose_ual():
    db = next(get_db())
    
    print("=" * 80)
    print("UAL财报（ID: 90）快速诊断")
    print("=" * 80)
    
    filing = db.query(Filing).filter(Filing.id == 90).first()
    
    print("\n1. 基本信息:")
    print(f"  - 状态: {filing.status}")
    print(f"  - AI摘要: {filing.ai_summary[:100] if filing.ai_summary else 'None'}...")
    
    # 检查文件
    data_dir = Path("data/filings")
    print(f"\n2. 检查所有可能的文件位置:")
    
    # 尝试不同的路径格式
    possible_paths = []
    
    if hasattr(filing, 'accession_number') and filing.accession_number:
        cik = filing.company.cik.lstrip('0')
        acc_no = filing.accession_number.replace('-', '')
        possible_paths.append(data_dir / cik / acc_no)
        possible_paths.append(data_dir / filing.company.ticker / acc_no)
        possible_paths.append(data_dir / f"{filing.company.ticker}_{filing.id}")
    
    file_found = False
    for path in possible_paths:
        if path.exists():
            print(f"  ✅ 找到文件目录: {path}")
            files = list(path.glob("*"))
            print(f"     文件数: {len(files)}")
            for f in files[:3]:  # 只显示前3个
                print(f"     - {f.name} ({f.stat().st_size / 1024:.1f} KB)")
            file_found = True
            break
    
    if not file_found:
        print("  ❌ 没有找到下载的文件")
        # 检查整个data目录
        all_dirs = list(data_dir.glob("*/*"))
        print(f"  data/filings下共有 {len(all_dirs)} 个目录")
    
    # 检查关键字段
    print("\n3. 检查关键字段:")
    important_fields = [
        'ai_summary',
        'sentiment',
        'key_points',
        'financial_highlights',
        'quarterly_revenue',
        'quarterly_earnings',
        'expectations_comparison',
        'guidance_updates',
        'market_impact_10q'
    ]
    
    for field in important_fields:
        if hasattr(filing, field):
            value = getattr(filing, field)
            if value:
                if isinstance(value, str):
                    print(f"  ✅ {field}: {value[:50]}...")
                elif isinstance(value, (list, dict)):
                    print(f"  ✅ {field}: {json.dumps(value)[:50]}...")
                else:
                    print(f"  ✅ {field}: {value}")
            else:
                print(f"  ❌ {field}: None/Empty")
        else:
            print(f"  ⚠️  {field}: 字段不存在")
    
    print("\n4. 结论:")
    if filing.ai_summary and "United Airlines exceeds revenue" in filing.ai_summary:
        print("  ✅ AI处理过了（有摘要）")
        print("  ❌ 但是差异化字段都是空的")
        print("  🔧 可能原因：")
        print("     1. AI处理器没有提取差异化字段")
        print("     2. 字段映射有问题")
        print("     3. 数据库保存失败")
    else:
        print("  ❌ 看起来AI处理有问题")


if __name__ == "__main__":
    diagnose_ual()
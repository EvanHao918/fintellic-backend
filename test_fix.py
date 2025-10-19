#!/usr/bin/env python3
import sys
sys.path.append('.')

# 使用修复后的代码测试
from app.services.filing_downloader import filing_downloader
from pathlib import Path

test_cases = [
    ("data/filings/0001043277/000104327725000031", "10-K"),  # CHRW
    ("data/filings/0001094285/000109428525000123", "10-K"),  # TDY
]

for dir_path, filing_type in test_cases:
    path = Path(dir_path)
    if path.exists():
        index_file = path / "index.htm"
        if index_file.exists():
            print(f"\n{path.name} ({filing_type}):")
            with open(index_file, 'r') as f:
                content = f.read()
                result = filing_downloader._parse_index_enhanced(content, filing_type)
                if result:
                    print(f"  ✅ Found: {result['filename']}")
                    print(f"     URL: {result['url']}")
                else:
                    print(f"  ❌ Failed")

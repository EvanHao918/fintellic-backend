#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append('.')

from app.services.filing_downloader import filing_downloader
from bs4 import BeautifulSoup

# 测试失败的8个案例
test_cases = [
    "data/filings/0001043277/000104327725000031",  # CHRW
    "data/filings/0001094285/000109428525000123",  # TDY
]

for dir_path in test_cases:
    path = Path(dir_path)
    if path.exists():
        index_file = path / "index.htm"
        if index_file.exists():
            print(f"\n{path.name}:")
            with open(index_file, 'r') as f:
                content = f.read()
                
                # 测试现有的解析逻辑
                soup = BeautifulSoup(content, 'html.parser')
                
                # 查找iXBRL链接
                ixbrl_links = soup.find_all('a', href=lambda x: x and '/ix?doc=' in x)
                print(f"  Found {len(ixbrl_links)} iXBRL links")
                
                for link in ixbrl_links[:3]:
                    href = link.get('href', '')
                    text = link.text.strip()
                    
                    # 测试提取逻辑
                    extracted = filing_downloader._extract_url_from_ixbrl_link(href)
                    print(f"  Link: {text[:30]}")
                    print(f"    Original: {href[:80]}")
                    print(f"    Extracted: {extracted[:80]}")
                    
                # 测试enhanced parser
                result = filing_downloader._parse_index_enhanced(content, "10-K")
                if result:
                    print(f"  ✅ Parser found: {result['filename']}")
                else:
                    print(f"  ❌ Parser failed to find document")

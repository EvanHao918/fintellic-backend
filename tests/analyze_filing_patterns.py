#!/usr/bin/env python3
import os
import re
from pathlib import Path
from collections import Counter
from bs4 import BeautifulSoup

# 分析已下载的财报文件模式
filing_dir = Path("data/filings")
patterns = Counter()
success_cases = []
failed_cases = []

for company_dir in filing_dir.iterdir():
    if company_dir.is_dir():
        for accession_dir in company_dir.iterdir():
            if accession_dir.is_dir():
                files = list(accession_dir.glob("*.htm")) + list(accession_dir.glob("*.html"))
                
                # 分类成功和失败
                if len(files) > 1:  # 有index和主文档
                    success_cases.append(accession_dir)
                    # 提取文件名模式
                    for f in files:
                        if 'index' not in f.name.lower():
                            # 规范化模式
                            pattern = re.sub(r'\d{8}', 'YYYYMMDD', f.name)
                            pattern = re.sub(r'\d{6}', 'YYMMDD', pattern)
                            pattern = re.sub(r'\d{4}', 'YYYY', pattern)
                            patterns[pattern] += 1
                elif len(files) == 1:  # 只有index
                    failed_cases.append(accession_dir)

print(f"成功案例: {len(success_cases)}")
print(f"失败案例: {len(failed_cases)}")
print("\n最常见的文件名模式:")
for pattern, count in patterns.most_common(10):
    print(f"  {count:3d} : {pattern}")

# 分析失败案例的index文件
print("\n分析失败案例...")
for case in failed_cases[:5]:
    index_files = list(case.glob("*index.htm*"))
    if index_files:
        print(f"\n{case.name}:")
        with open(index_files[0], 'r', encoding='utf-8', errors='ignore') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
            # 查找可能的主文档链接
            for link in soup.find_all('a', href=True)[:10]:
                if not 'index' in link['href'].lower():
                    print(f"  -> {link.get('href')} : {link.text.strip()[:30]}")

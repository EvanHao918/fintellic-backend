#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

print("=== STEP 11: 检查实际代码实现 ===\n")

# 1. 检查 AI 处理器的方法签名
print("1. 检查 AIProcessor.process_filing 方法签名:")
ai_processor_path = Path("app/services/ai_processor.py")

if ai_processor_path.exists():
    with open(ai_processor_path, 'r') as f:
        content = f.read()
        
    # 查找 process_filing 方法
    import re
    pattern = r'async def process_filing.*?(?=\n    [a-zA-Z]|\n\s*async def|\nclass|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    if matches:
        print("找到 process_filing 方法:")
        print("-" * 50)
        print(matches[0][:500] + "..." if len(matches[0]) > 500 else matches[0])
        print("-" * 50)

# 2. 检查下载器的 CIK 处理
print("\n\n2. 检查 FilingDownloader 的 URL 构建:")
downloader_path = Path("app/services/filing_downloader.py")

if downloader_path.exists():
    with open(downloader_path, 'r') as f:
        lines = f.readlines()
        
    # 查找 URL 构建相关代码
    for i, line in enumerate(lines):
        if 'Archives/edgar/data' in line or 'cik' in line.lower() and 'url' in line.lower():
            print(f"Line {i+1}: {line.strip()}")
            # 打印上下文
            for j in range(max(0, i-2), min(len(lines), i+3)):
                if j != i:
                    print(f"Line {j+1}: {lines[j].strip()}")
            print()

# 3. 测试不同的 CIK 格式
print("\n3. 测试 CIK 格式处理:")
test_cik = "0000789019"
print(f"原始 CIK: {test_cik}")
print(f"去除前导零: {test_cik.lstrip('0')}")
print(f"保持 10 位: {test_cik}")

# 4. 检查失败的 URL
print("\n4. 分析失败的 URL:")
failed_url = "https://www.sec.gov/Archives/edgar/data/789019/000078901924000789/0000789019-24-000789-index.htm"
print(f"失败的 URL: {failed_url}")
print("注意: CIK 部分使用了去除前导零的格式 (789019)，但应该使用原始格式 (0000789019)")

print("\n\n建议修复:")
print("1. 确保下载器使用正确的 CIK 格式（保持前导零）")
print("2. 检查 AI 处理器的方法参数")

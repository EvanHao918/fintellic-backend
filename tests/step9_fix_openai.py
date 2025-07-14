#!/usr/bin/env python3
import sys
from pathlib import Path

print("=== STEP 9: 修复 OpenAI API 兼容性 ===\n")

# 1. 检查当前 OpenAI 版本
try:
    import openai
    print(f"当前 OpenAI 版本: {openai.__version__}")
except Exception as e:
    print(f"无法导入 OpenAI: {e}")

# 2. 查看 AI 处理器代码
print("\n查看 AI 处理器代码位置:")
ai_processor_path = Path("app/services/ai_processor.py")
if ai_processor_path.exists():
    print(f"✅ 找到 AI 处理器: {ai_processor_path}")
    
    # 读取前50行看看使用的API
    with open(ai_processor_path, 'r') as f:
        lines = f.readlines()[:50]
        
    print("\n检查 OpenAI API 使用方式:")
    for i, line in enumerate(lines):
        if 'openai' in line.lower() or 'completion' in line.lower():
            print(f"Line {i+1}: {line.strip()}")

# 3. 检查 requirements.txt
print("\n\n检查 requirements.txt 中的 OpenAI 版本:")
req_path = Path("requirements.txt")
if req_path.exists():
    with open(req_path, 'r') as f:
        for line in f:
            if 'openai' in line.lower():
                print(f"要求: {line.strip()}")

print("\n\n解决方案选项:")
print("1. 降级到兼容版本: pip install openai==0.28.1")
print("2. 或更新代码以使用新版本 API")

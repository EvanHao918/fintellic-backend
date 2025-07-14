#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from app.core.database import SessionLocal
from app.models import Filing, ProcessingStatus
from app.core.config import settings
import os

print("=== STEP 8: 诊断处理失败原因 ===\n")

db = SessionLocal()

try:
    # 1. 检查环境配置
    print("1. 检查环境配置:")
    print(f"   OPENAI_API_KEY 设置: {'✅ 已设置' if settings.OPENAI_API_KEY else '❌ 未设置'}")
    print(f"   OPENAI_API_KEY 长度: {len(settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else 0}")
    print(f"   SEC_USER_AGENT: {settings.SEC_USER_AGENT}")
    print(f"   SEC_ARCHIVE_URL: {settings.SEC_ARCHIVE_URL}")
    
    # 2. 检查文件存储目录
    print("\n2. 检查文件存储:")
    data_dir = Path("data/filings")
    print(f"   数据目录存在: {'✅' if data_dir.exists() else '❌'}")
    if data_dir.exists():
        print(f"   目录权限: {'✅ 可写' if os.access(data_dir, os.W_OK) else '❌ 不可写'}")
    
    # 3. 获取失败任务的详细信息
    print("\n3. 失败任务详细分析:")
    failed_filings = db.query(Filing).filter(
        Filing.status == ProcessingStatus.FAILED
    ).limit(3).all()
    
    for filing in failed_filings:
        print(f"\n{filing.company.ticker} - {filing.filing_type.value}:")
        print(f"   Accession: {filing.accession_number}")
        print(f"   CIK: {filing.company.cik}")
        print(f"   错误: {filing.error_message}")
        
        # 构建预期的URL
        acc_no_clean = filing.accession_number.replace("-", "")
        expected_url = f"{settings.SEC_ARCHIVE_URL}/{filing.company.cik}/{acc_no_clean}/"
        print(f"   预期URL: {expected_url}")
        
        # 检查是否是老财报
        if filing.filing_date:
            print(f"   财报日期: {filing.filing_date}")
            
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()

# 4. 测试 OpenAI 连接
print("\n4. 测试 OpenAI API:")
if settings.OPENAI_API_KEY:
    try:
        import openai
        openai.api_key = settings.OPENAI_API_KEY
        
        # 简单测试
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Say 'API working'"}],
            max_tokens=10
        )
        print("   ✅ OpenAI API 连接成功")
    except Exception as e:
        print(f"   ❌ OpenAI API 错误: {e}")
else:
    print("   ❌ OPENAI_API_KEY 未设置")

# 5. 检查 .env 文件
print("\n5. 检查 .env 文件:")
env_file = Path(".env")
if env_file.exists():
    print("   ✅ .env 文件存在")
    with open(env_file, 'r') as f:
        content = f.read()
        has_openai = "OPENAI_API_KEY" in content
        print(f"   OPENAI_API_KEY 在 .env 中: {'✅' if has_openai else '❌'}")
else:
    print("   ❌ .env 文件不存在")

#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import asyncio
from app.core.database import SessionLocal
from app.models import Filing, ProcessingStatus
from app.services.filing_downloader import FilingDownloader
from app.services.text_extractor import TextExtractor
from app.services.ai_processor import AIProcessor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_fixed_processing():
    print("=== STEP 12: 测试修复后的处理流程 ===\n")
    
    db = SessionLocal()
    
    try:
        # 获取一个失败的财报
        failed_filing = db.query(Filing).filter(
            Filing.status == ProcessingStatus.FAILED
        ).first()
        
        if not failed_filing:
            print("没有失败的财报需要处理")
            return
            
        print(f"测试财报: {failed_filing.company.ticker} - {failed_filing.filing_type.value}")
        print(f"CIK: {failed_filing.company.cik}")
        print(f"Accession: {failed_filing.accession_number}")
        
        # 1. 测试修复的 URL
        acc_no_clean = failed_filing.accession_number.replace("-", "")
        
        # 测试两种 URL 格式
        urls_to_test = [
            # 保持完整 CIK
            f"https://www.sec.gov/Archives/edgar/data/{failed_filing.company.cik}/{acc_no_clean}/{failed_filing.accession_number}-index.htm",
            # 去除前导零
            f"https://www.sec.gov/Archives/edgar/data/{failed_filing.company.cik.lstrip('0')}/{acc_no_clean}/{failed_filing.accession_number}-index.htm"
        ]
        
        print("\n测试不同的 URL 格式:")
        import httpx
        async with httpx.AsyncClient() as client:
            for url in urls_to_test:
                try:
                    response = await client.head(url, timeout=10.0)
                    print(f"{response.status_code} - {url}")
                except Exception as e:
                    print(f"ERROR - {url}: {e}")
        
        # 2. 手动处理流程
        print("\n\n手动执行处理流程:")
        
        # 重置状态
        failed_filing.status = ProcessingStatus.PROCESSING
        failed_filing.error_message = None
        db.commit()
        
        # Step 1: 下载
        print("\n1. 下载财报...")
        downloader = FilingDownloader()
        download_success = await downloader.download_filing(db, failed_filing)
        
        if not download_success:
            print("❌ 下载失败")
            # 检查是否是老财报（可能已经不在 SEC 网站上）
            filing_age = (datetime.now() - failed_filing.filing_date).days if failed_filing.filing_date else 0
            print(f"财报年龄: {filing_age} 天")
            if filing_age > 30:
                print("这是一个老财报，可能已经被归档或移动")
            return
        
        print("✅ 下载成功")
        
        # Step 2: 提取文本
        print("\n2. 提取文本...")
        extractor = TextExtractor()
        text = await extractor.extract_text(db, failed_filing)
        
        if not text:
            print("❌ 文本提取失败")
            return
            
        print(f"✅ 提取文本成功 ({len(text)} 字符)")
        
        # Step 3: AI 处理
        print("\n3. AI 分析...")
        ai_processor = AIProcessor()
        ai_success = await ai_processor.process_filing(db, failed_filing)
        
        if ai_success:
            print("✅ AI 分析成功")
            # 刷新对象
            db.refresh(failed_filing)
            if failed_filing.ai_summary:
                print(f"摘要: {failed_filing.ai_summary[:100]}...")
        else:
            print("❌ AI 分析失败")
            
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

# 导入必要的模块
from datetime import datetime

if __name__ == "__main__":
    asyncio.run(test_fixed_processing())

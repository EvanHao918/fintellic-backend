#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import asyncio
from app.services.filing_downloader import FilingDownloader
from app.services.ai_processor import AIProcessor
from app.core.database import SessionLocal
from app.models import Filing, ProcessingStatus
from app.core.config import settings

async def debug_failures():
    print("=== STEP 10: 深入调试失败原因 ===\n")
    
    db = SessionLocal()
    
    try:
        # 1. 测试下载功能
        print("1. 测试财报下载功能:")
        
        # 获取一个失败的财报
        failed_filing = db.query(Filing).filter(
            Filing.status == ProcessingStatus.FAILED,
            Filing.error_message.like('%download%')
        ).first()
        
        if failed_filing:
            print(f"测试下载: {failed_filing.company.ticker} - {failed_filing.filing_type.value}")
            print(f"Accession: {failed_filing.accession_number}")
            
            downloader = FilingDownloader()
            
            # 构建测试 URL
            acc_no_clean = failed_filing.accession_number.replace("-", "")
            test_url = f"{settings.SEC_ARCHIVE_URL}/{failed_filing.company.cik}/{acc_no_clean}/"
            print(f"测试 URL: {test_url}")
            
            # 尝试下载
            try:
                success = await downloader.download_filing(db, failed_filing)
                print(f"下载结果: {'✅ 成功' if success else '❌ 失败'}")
            except Exception as e:
                print(f"下载错误: {e}")
                import traceback
                traceback.print_exc()
        
        # 2. 测试 AI 处理
        print("\n\n2. 测试 AI 处理功能:")
        
        # 创建测试文本
        test_text = """
        This is a test 10-K filing for testing purposes.
        
        ITEM 1. BUSINESS
        We are a technology company that develops software.
        
        ITEM 1A. RISK FACTORS
        Competition may affect our business.
        
        ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS
        Revenue increased by 15% this year.
        """
        
        ai_processor = AIProcessor()
        
        print("测试 AI 摘要生成...")
        try:
            result = await ai_processor.process_filing(
                filing_text=test_text,
                company_name="Test Company",
                form_type="10-K"
            )
            
            if result:
                print("✅ AI 处理成功!")
                print(f"摘要: {result.get('summary', '')[:100]}...")
                print(f"情绪分析: {result.get('sentiment', {})}")
            else:
                print("❌ AI 处理返回空结果")
                
        except Exception as e:
            print(f"❌ AI 处理错误: {e}")
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(debug_failures())

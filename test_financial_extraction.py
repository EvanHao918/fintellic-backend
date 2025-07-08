# 创建一个测试脚本 test_financial_extraction.py
from app.core.database import SessionLocal
from app.models.filing import Filing
from app.services.ai_processor import ai_processor
import asyncio

async def test_extraction():
    db = SessionLocal()
    # 获取一个已有的财报
    filing = db.query(Filing).filter(Filing.filing_type == "10-Q").first()
    if filing:
        print(f"Testing with filing: {filing.company.ticker} - {filing.filing_type}")
        result = await ai_processor.process_filing(db, filing)
        print(f"Result: {result}")
        print(f"Financial data: {filing.financial_highlights}")
    db.close()

asyncio.run(test_extraction())
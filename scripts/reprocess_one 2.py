import asyncio
import sys
sys.path.append('.')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.filing import Filing, ProcessingStatus
from app.services.ai_processor import ai_processor

# 创建数据库连接
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async def main():
    db = SessionLocal()
    # 找一个失败的财报
    filing = db.query(Filing).filter(
        Filing.status == ProcessingStatus.FAILED
    ).first()
    
    if filing:
        print(f"Reprocessing {filing.company.ticker} {filing.filing_type.value}")
        filing.status = ProcessingStatus.PENDING
        filing.error_message = None
        db.commit()
        
        try:
            result = await ai_processor.process_filing(db, filing)
            print(f"Result: {result}")
            if result:
                print("✅ Processing successful!")
                db.refresh(filing)
                print(f"Status: {filing.status}")
                print(f"Has AI summary: {bool(filing.ai_summary)}")
                print(f"Has market impact: {bool(filing.market_impact_10k or filing.market_impact_10q)}")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("No failed filings found")
    
    db.close()

asyncio.run(main())

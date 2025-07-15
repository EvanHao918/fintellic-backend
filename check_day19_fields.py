from app.core.database import SessionLocal
from app.models import Filing

db = SessionLocal()

def check_filing(filing_id, filing_type):
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if filing:
        print(f"\n{'='*50}")
        print(f"Filing ID {filing_id} ({filing_type})")
        print(f"{'='*50}")
        
        # 基本信息
        print(f"Filing Type: {filing.filing_type}")
        print(f"Company ID: {filing.company_id}")
        print(f"Status: {filing.status}")
        
        # 通用新字段
        print(f"\n通用字段:")
        print(f"  fiscal_year: {filing.fiscal_year}")
        print(f"  fiscal_quarter: {filing.fiscal_quarter}")
        print(f"  period_end_date: {filing.period_end_date}")
        
        if filing_type == "8-K":
            print(f"\n8-K 专用字段:")
            print(f"  item_type: {filing.item_type}")
            print(f"  items: {filing.items}")
            print(f"  event_timeline: {filing.event_timeline}")
            print(f"  event_nature_analysis: {filing.event_nature_analysis}")
            print(f"  market_impact_analysis: {filing.market_impact_analysis}")
            print(f"  key_considerations: {filing.key_considerations}")
        
        elif filing_type == "10-Q":
            print(f"\n10-Q 专用字段:")
            print(f"  expectations_comparison: {filing.expectations_comparison}")
            print(f"  cost_structure: {filing.cost_structure}")
            print(f"  guidance_update: {filing.guidance_update}")
            print(f"  growth_decline_analysis: {filing.growth_decline_analysis}")
            print(f"  management_tone_analysis: {filing.management_tone_analysis}")
            print(f"  beat_miss_analysis: {filing.beat_miss_analysis}")

# 检查8-K
check_filing(6, "8-K")

# 检查10-Q
check_filing(25, "10-Q")

db.close()

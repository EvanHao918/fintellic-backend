from app.core.database import SessionLocal
from app.models import Filing

db = SessionLocal()

# 检查所有字段
def check_filing(filing_id):
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if filing:
        print(f"\nFiling ID {filing_id}:")
        # 使用 getattr 来安全获取属性
        print(f"  form_type: {filing.form_type}")
        print(f"  fiscal_year: {getattr(filing, 'fiscal_year', 'N/A')}")
        print(f"  fiscal_quarter: {getattr(filing, 'fiscal_quarter', 'N/A')}")
        print(f"  period_end_date: {getattr(filing, 'period_end_date', 'N/A')}")
        
        if filing_id == 6:  # 8-K
            print(f"  item_type: {getattr(filing, 'item_type', 'N/A')}")
            print(f"  event_timeline: {getattr(filing, 'event_timeline', 'N/A')}")
            print(f"  items: {getattr(filing, 'items', 'N/A')}")
            print(f"  event_nature_analysis: {getattr(filing, 'event_nature_analysis', 'N/A')}")
            print(f"  market_impact_analysis: {getattr(filing, 'market_impact_analysis', 'N/A')}")
            print(f"  key_considerations: {getattr(filing, 'key_considerations', 'N/A')}")
        
        if filing_id == 25:  # 10-Q
            print(f"  expectations_comparison: {getattr(filing, 'expectations_comparison', 'N/A')}")
            print(f"  cost_structure: {getattr(filing, 'cost_structure', 'N/A')}")
            print(f"  guidance_update: {getattr(filing, 'guidance_update', 'N/A')}")
            print(f"  growth_decline_analysis: {getattr(filing, 'growth_decline_analysis', 'N/A')}")
            print(f"  management_tone_analysis: {getattr(filing, 'management_tone_analysis', 'N/A')}")
            print(f"  beat_miss_analysis: {getattr(filing, 'beat_miss_analysis', 'N/A')}")

check_filing(6)
check_filing(25)

# 也让我们检查Filing模型有哪些属性
print("\n\nFiling model attributes:")
filing = db.query(Filing).first()
if filing:
    attrs = [attr for attr in dir(filing) if not attr.startswith('_')]
    print(attrs)

db.close()

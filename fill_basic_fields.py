from app.core.database import SessionLocal
from app.models import Filing
from datetime import datetime

db = SessionLocal()

# 更新fiscal_year和fiscal_quarter
def update_filing_dates(filing_id):
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if filing:
        # 从filing_date提取fiscal_year
        if filing.filing_date and not filing.fiscal_year:
            filing.fiscal_year = str(filing.filing_date.year)
            print(f"Updated filing {filing_id} fiscal_year to: {filing.fiscal_year}")
        
        # 如果是10-Q，确保fiscal_quarter已设置
        if filing.filing_type.name == "FORM_10Q" and filing.fiscal_quarter:
            print(f"Filing {filing_id} already has fiscal_quarter: {filing.fiscal_quarter}")
        
        db.commit()

# 更新两个测试filing
update_filing_dates(6)
update_filing_dates(25)

# 添加一些测试的cost_structure数据
filing25 = db.query(Filing).filter(Filing.id == 25).first()
if filing25 and not filing25.cost_structure:
    filing25.cost_structure = {
        "revenue": 100000000,
        "cost_of_revenue": 60000000,
        "gross_profit": 40000000,
        "operating_expenses": {
            "r_and_d": 15000000,
            "sales_and_marketing": 10000000,
            "general_and_admin": 5000000
        },
        "operating_income": 10000000
    }
    db.commit()
    print("Added cost_structure to filing 25")

db.close()

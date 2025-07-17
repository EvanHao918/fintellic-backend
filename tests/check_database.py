from app.database import SessionLocal
from app.models import Filing
import json

db = SessionLocal()

print("Checking Filing ID 6 (8-K)...")
filing6 = db.query(Filing).filter(Filing.id == 6).first()
if filing6:
    print(f"ID: {filing6.id}")
    print(f"Type: {filing6.type}")
    print(f"Item Type: {filing6.item_type}")
    print(f"Event Timeline: {filing6.event_timeline}")
    print(f"Items: {filing6.items}")
    print(f"Fiscal Year: {filing6.fiscal_year}")
    print(f"Fiscal Quarter: {filing6.fiscal_quarter}")
    print(f"Period End Date: {filing6.period_end_date}")
else:
    print("Filing 6 not found")

print("\n" + "="*50 + "\n")

print("Checking Filing ID 25 (10-Q)...")
filing25 = db.query(Filing).filter(Filing.id == 25).first()
if filing25:
    print(f"ID: {filing25.id}")
    print(f"Type: {filing25.type}")
    print(f"Expectations Comparison: {filing25.expectations_comparison}")
    print(f"Cost Structure: {filing25.cost_structure}")
    print(f"Guidance Update: {filing25.guidance_update}")
    print(f"Fiscal Year: {filing25.fiscal_year}")
    print(f"Fiscal Quarter: {filing25.fiscal_quarter}")
else:
    print("Filing 25 not found")

db.close()

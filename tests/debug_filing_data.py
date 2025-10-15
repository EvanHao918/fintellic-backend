# scripts/debug_filing_data.py
"""
Debug script to check filing data in database
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.filing import Filing

def debug_filing(filing_id: int):
    """Debug a specific filing's data"""
    db = SessionLocal()
    
    try:
        filing = db.query(Filing).filter(Filing.id == filing_id).first()
        
        if not filing:
            print(f"Filing {filing_id} not found")
            return
        
        print(f"\n=== Filing {filing_id} Debug Info ===")
        print(f"Company: {filing.company.ticker if filing.company else 'None'}")
        print(f"Filing Type: {filing.filing_type.value}")
        print(f"Status: {filing.status.value}")
        
        # Check financial_highlights field
        print(f"\nfinancial_highlights type: {type(filing.financial_highlights)}")
        print(f"financial_highlights content: {filing.financial_highlights[:200] if filing.financial_highlights else 'None'}")
        
        # Check all 10-Q specific fields
        if filing.filing_type.value == "10-Q":
            print("\n=== 10-Q Specific Fields ===")
            fields = [
                'expectations_comparison',
                'cost_structure',
                'guidance_update',
                'growth_decline_analysis',
                'management_tone_analysis',
                'beat_miss_analysis',
                'market_impact_10q'
            ]
            
            for field in fields:
                value = getattr(filing, field, None)
                print(f"{field}: {type(value)} - {str(value)[:100] if value else 'None'}")
        
        # Check if any fields are storing JSON/dict when they should be text
        print("\n=== Checking for JSON/Dict fields ===")
        for attr in dir(filing):
            if not attr.startswith('_'):
                value = getattr(filing, attr, None)
                if isinstance(value, dict):
                    print(f"WARNING: {attr} is a dict: {value}")
                elif isinstance(value, list) and attr not in ['key_tags', 'key_questions']:
                    print(f"WARNING: {attr} is a list: {value}")
        
    finally:
        db.close()

if __name__ == "__main__":
    filing_id = 380  # The filing causing the error
    debug_filing(filing_id)
"""
Script to check the actual database model attributes
"""
import sys
sys.path.append('.')

from app.models.filing import Filing
from app.models.company import Company
from app.core.database import SessionLocal

def check_models():
    print("=== Filing Model Attributes ===")
    # Get all attributes of Filing model
    filing_attrs = [attr for attr in dir(Filing) if not attr.startswith('_')]
    print("Filing attributes:", filing_attrs)
    
    print("\n=== Company Model Attributes ===")
    # Get all attributes of Company model
    company_attrs = [attr for attr in dir(Company) if not attr.startswith('_')]
    print("Company attributes:", company_attrs)
    
    # Check database
    db = SessionLocal()
    try:
        # Get a sample filing if exists
        filing = db.query(Filing).first()
        if filing:
            print("\n=== Sample Filing Data ===")
            print(f"Filing ID: {filing.id}")
            print(f"Attributes: {filing.__dict__.keys()}")
            
            # Try to get company
            if hasattr(filing, 'company_cik'):
                print(f"Company CIK: {filing.company_cik}")
            if hasattr(filing, 'cik'):
                print(f"CIK: {filing.cik}")
                
        # Get a sample company
        company = db.query(Company).first()
        if company:
            print("\n=== Sample Company Data ===")
            print(f"Company: {company.ticker}")
            print(f"CIK: {company.cik}")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_models()
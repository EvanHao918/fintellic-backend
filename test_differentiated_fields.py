#!/usr/bin/env python3
"""
Test script for Day 19 differentiated fields (Fixed version)
"""
from datetime import datetime
from app.core.database import SessionLocal
from app.models.filing import Filing, FilingType
from app.services.filing_data_extractor import FilingDataExtractor, process_filing_data

def test_new_fields():
    """Test the new differentiated display fields"""
    db = SessionLocal()
    
    try:
        print("=== Testing New Fields ===")
        
        # Find different types of filings
        filing_types = ["10-K", "10-Q", "8-K", "S-1"]
        
        for filing_type in filing_types:
            filing = db.query(Filing).filter(
                Filing.filing_type == filing_type
            ).first()
            
            if filing:
                print(f"\n{filing_type} Filing (ID: {filing.id}):")
                print(f"  Company: {filing.company.ticker}")
                print(f"  Date: {filing.filing_date}")
                
                # Test common fields
                print(f"  Fiscal Year: {filing.fiscal_year}")
                print(f"  Fiscal Quarter: {filing.fiscal_quarter}")
                
                # Test type-specific fields
                if filing_type == "10-K":
                    print(f"  Auditor Opinion: {filing.auditor_opinion[:50] if filing.auditor_opinion else 'None'}")
                    print(f"  Business Segments: {filing.business_segments}")
                    
                elif filing_type == "10-Q":
                    print(f"  Expectations Comparison: {filing.expectations_comparison}")
                    print(f"  Guidance Update: {filing.guidance_update}")
                    
                elif filing_type == "8-K":
                    print(f"  Item Type: {filing.item_type}")
                    print(f"  Event Timeline: {filing.event_timeline}")
                    
                elif filing_type == "S-1":
                    print(f"  IPO Details: {filing.ipo_details}")
                    print(f"  Company Overview: {filing.company_overview[:50] if filing.company_overview else 'None'}")
        
        print("\n=== Testing Data Extraction ===")
        
        # Test 8-K data extraction
        sample_8k_content = """
        UNITED STATES
        SECURITIES AND EXCHANGE COMMISSION
        
        FORM 8-K
        CURRENT REPORT
        
        Date of Report: January 15, 2024
        
        Item 5.02 Departure of Directors or Certain Officers
        
        On January 15, 2024, the Company announced that John Smith, 
        Chief Financial Officer, will be departing effective February 1, 2024.
        
        Item 8.01 Other Events
        
        The Company also announced a new strategic partnership.
        """
        
        extracted_data = process_filing_data("8-K", sample_8k_content)
        print("\nExtracted 8-K Data:")
        print(f"  Items: {extracted_data.get('items')}")
        print(f"  Item Type: {extracted_data.get('item_type')}")
        print(f"  Event Type: {extracted_data.get('event_type')}")
        print(f"  Timeline: {extracted_data.get('event_timeline')}")
        
        # Update a filing with extracted data
        test_filing = db.query(Filing).filter(
            Filing.filing_type == "8-K"
        ).first()
        
        if test_filing:
            print(f"\nUpdating filing {test_filing.id} with extracted data...")
            
            test_filing.items = extracted_data.get('items')
            test_filing.item_type = extracted_data.get('item_type')
            test_filing.event_timeline = extracted_data.get('event_timeline')
            test_filing.event_type = extracted_data.get('event_type')
            
            # Also update fiscal period if found
            test_filing.fiscal_year = extracted_data.get('fiscal_year')
            test_filing.fiscal_quarter = extracted_data.get('fiscal_quarter')
            
            db.commit()
            print(f"Successfully updated filing {test_filing.id}")
            
            # Verify the update
            db.refresh(test_filing)
            print(f"\nVerifying update:")
            print(f"  Item Type: {test_filing.item_type}")
            print(f"  Event Type: {test_filing.event_type}")
            print(f"  Event Timeline: {test_filing.event_timeline}")
        
        # Test updating a 10-Q with sample data
        test_10q = db.query(Filing).filter(
            Filing.filing_type == "10-Q"
        ).first()
        
        if test_10q:
            print(f"\nUpdating 10-Q filing {test_10q.id} with sample data...")
            
            test_10q.fiscal_quarter = "Q3 2024"
            test_10q.expectations_comparison = {
                "revenue": {
                    "expected": 1000000000,
                    "actual": 1050000000,
                    "beat": True
                },
                "eps": {
                    "expected": 1.25,
                    "actual": 1.30,
                    "beat": True
                },
                "guidance": {
                    "previous": "Revenue: $4.0-4.2B",
                    "updated": "Revenue: $4.1-4.3B",
                    "raised": True
                }
            }
            
            test_10q.guidance_update = {
                "updated": True,
                "revenue_guidance": "$4.1-4.3B (previously $4.0-4.2B)",
                "eps_guidance": "$5.20-5.40 (previously $5.00-5.20)",
                "key_assumptions": [
                    "Continued strong demand in cloud services",
                    "Stable supply chain",
                    "No major currency headwinds"
                ]
            }
            
            db.commit()
            print(f"Successfully updated 10-Q filing {test_10q.id}")
        
        print("\n=== Test Completed Successfully ===")
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


def test_api_response():
    """Test API response with new fields"""
    import requests
    
    print("\n=== Testing API Response ===")
    
    try:
        # Get filing list
        response = requests.get("http://localhost:8000/api/filings/")
        if response.status_code == 200:
            data = response.json()
            print(f"Found {data['total']} filings")
            
            # Test detailed view for different filing types
            for filing in data['data'][:5]:  # Test first 5
                filing_id = filing['id']
                form_type = filing['form_type']
                
                detail_response = requests.get(f"http://localhost:8000/api/filings/{filing_id}")
                if detail_response.status_code == 200:
                    detail_data = detail_response.json()
                    print(f"\n{form_type} Filing {filing_id}:")
                    
                    # Check for new fields based on type
                    if form_type == "10-K":
                        print(f"  Has auditor_opinion: {'auditor_opinion' in detail_data}")
                        print(f"  Has business_segments: {'business_segments' in detail_data}")
                    elif form_type == "10-Q":
                        print(f"  Has expectations_comparison: {'expectations_comparison' in detail_data}")
                        print(f"  Has guidance_update: {'guidance_update' in detail_data}")
                    elif form_type == "8-K":
                        print(f"  Has item_type: {'item_type' in detail_data}")
                        print(f"  Has event_timeline: {'event_timeline' in detail_data}")
                    elif form_type == "S-1":
                        print(f"  Has ipo_details: {'ipo_details' in detail_data}")
                        print(f"  Has company_overview: {'company_overview' in detail_data}")
                    
                    # Common fields
                    print(f"  Fiscal Year: {detail_data.get('fiscal_year')}")
                    print(f"  Fiscal Quarter: {detail_data.get('fiscal_quarter')}")
        else:
            print(f"Failed to get filings: {response.status_code}")
            print("Make sure the server is running: uvicorn app.main:app --reload")
    
    except Exception as e:
        print(f"API test error: {e}")
        print("Make sure the server is running: uvicorn app.main:app --reload")


if __name__ == "__main__":
    # First test database operations
    test_new_fields()
    
    # Then test API (requires server to be running)
    print("\n" + "="*50)
    input("Press Enter to test API (make sure server is running)...")
    test_api_response()
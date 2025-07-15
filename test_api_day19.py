#!/usr/bin/env python3
"""
Test API endpoints with authentication for Day 19
"""
import requests
import json

# API base URL
BASE_URL = "http://localhost:8000/api/v1"

# Test credentials
EMAIL = "test2@fintellic.com"
PASSWORD = "Test123456"


def login():
    """Login and get access token"""
    print("=== Logging in ===")
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={
            "username": EMAIL,
            "password": PASSWORD
        }
    )
    if response.status_code == 200:
        token_data = response.json()
        print("✓ Login successful")
        return token_data["access_token"]
    else:
        print(f"✗ Login failed: {response.text}")
        return None


def test_filings_api(token):
    """Test filing endpoints with new fields"""
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\n=== Testing Filing Endpoints ===")
    
    # Get filings list
    response = requests.get(f"{BASE_URL}/filings/", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Found {data['total']} filings")
        
        # Test specific filings we updated
        test_ids = [6, 25]  # 8-K and 10-Q we updated
        
        for filing_id in test_ids:
            print(f"\n--- Testing Filing ID {filing_id} ---")
            detail_response = requests.get(
                f"{BASE_URL}/filings/{filing_id}", 
                headers=headers
            )
            
            if detail_response.status_code == 200:
                filing_data = detail_response.json()
                form_type = filing_data.get('form_type')
                print(f"✓ Retrieved {form_type} filing")
                
                # Check new fields based on type
                if form_type == "8-K":
                    print("\n8-K Specific Fields:")
                    print(f"  - Item Type: {filing_data.get('item_type')}")
                    print(f"  - Event Type: {filing_data.get('event_type')}")
                    print(f"  - Event Timeline: {filing_data.get('event_timeline')}")
                    print(f"  - Items: {filing_data.get('items')}")
                    
                elif form_type == "10-Q":
                    print("\n10-Q Specific Fields:")
                    print(f"  - Fiscal Quarter: {filing_data.get('fiscal_quarter')}")
                    print(f"  - Expectations Comparison: {json.dumps(filing_data.get('expectations_comparison'), indent=2)}")
                    print(f"  - Guidance Update: {json.dumps(filing_data.get('guidance_update'), indent=2)}")
                
                # Common fields
                print("\nCommon Fields:")
                print(f"  - Company: {filing_data['company']['ticker']}")
                print(f"  - Filing Date: {filing_data.get('filing_date')}")
                print(f"  - AI Summary: {filing_data.get('ai_summary')[:100] if filing_data.get('ai_summary') else 'None'}...")
                
            else:
                print(f"✗ Failed to get filing {filing_id}: {detail_response.status_code}")
                print(f"  Response: {detail_response.text}")
    else:
        print(f"✗ Failed to get filings list: {response.status_code}")
        print(f"  Response: {response.text}")


def test_all_filing_types(token):
    """Test all filing types to see new fields"""
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\n=== Testing All Filing Types ===")
    
    # Get filings of each type
    filing_types = ["10-K", "10-Q", "8-K", "S-1"]
    
    for filing_type in filing_types:
        print(f"\n--- {filing_type} Filings ---")
        response = requests.get(
            f"{BASE_URL}/filings/",
            headers=headers,
            params={"form_type": filing_type, "limit": 1}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['data']:
                filing = data['data'][0]
                filing_id = filing['id']
                
                # Get detailed view
                detail_response = requests.get(
                    f"{BASE_URL}/filings/{filing_id}",
                    headers=headers
                )
                
                if detail_response.status_code == 200:
                    filing_data = detail_response.json()
                    print(f"✓ {filing_type} Filing ID {filing_id} - {filing_data['company']['ticker']}")
                    
                    # Print type-specific fields
                    if filing_type == "10-K":
                        print(f"  - Auditor Opinion: {'Yes' if filing_data.get('auditor_opinion') else 'No'}")
                        print(f"  - Business Segments: {'Yes' if filing_data.get('business_segments') else 'No'}")
                        print(f"  - Three Year Financials: {'Yes' if filing_data.get('three_year_financials') else 'No'}")
                    
                    elif filing_type == "10-Q":
                        print(f"  - Expectations Comparison: {'Yes' if filing_data.get('expectations_comparison') else 'No'}")
                        print(f"  - Cost Structure: {'Yes' if filing_data.get('cost_structure') else 'No'}")
                        print(f"  - Guidance Update: {'Yes' if filing_data.get('guidance_update') else 'No'}")
                    
                    elif filing_type == "8-K":
                        print(f"  - Item Type: {filing_data.get('item_type') or 'No'}")
                        print(f"  - Event Timeline: {'Yes' if filing_data.get('event_timeline') else 'No'}")
                        print(f"  - Items: {'Yes' if filing_data.get('items') else 'No'}")
                    
                    elif filing_type == "S-1":
                        print(f"  - IPO Details: {'Yes' if filing_data.get('ipo_details') else 'No'}")
                        print(f"  - Company Overview: {'Yes' if filing_data.get('company_overview') else 'No'}")
                        print(f"  - Financial Summary: {'Yes' if filing_data.get('financial_summary') else 'No'}")
            else:
                print(f"  No {filing_type} filings found")


def main():
    """Run all tests"""
    # Login
    token = login()
    if not token:
        print("Failed to login. Exiting.")
        return
    
    # Test specific filings we updated
    test_filings_api(token)
    
    # Test all filing types
    test_all_filing_types(token)
    
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    main()
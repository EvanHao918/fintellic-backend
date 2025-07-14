#!/usr/bin/env python3
"""
Test view limits with actual filing IDs
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000/api/v1"

def test_view_limits():
    print("=== Testing Free User View Limits ===\n")
    
    # First, get list of available filings
    print("1. Getting available filings...")
    filings_response = requests.get(f"{BASE_URL}/filings?limit=10")
    if filings_response.status_code == 200:
        filings_data = filings_response.json()
        filing_ids = [f["id"] for f in filings_data.get("data", [])]
        print(f"Found {len(filing_ids)} filings: {filing_ids}")
    else:
        print("Failed to get filings list")
        return
    
    if len(filing_ids) < 4:
        print("\n⚠️  Need at least 4 filings to properly test limits.")
        print("Run 'python add_test_filings.py' to add more test data.")
        return
    
    # Login as test user
    print("\n2. Logging in as test2@fintellic.com...")
    login_response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": "test2@fintellic.com", "password": "Test123456"}
    )
    
    if login_response.status_code != 200:
        print(f"Login failed: {login_response.text}")
        print("\nTrying to create user first...")
        register_response = requests.post(
            f"{BASE_URL}/auth/register",
            json={
                "email": "test2@fintellic.com",
                "username": "testuser2",
                "password": "Test123456",
                "full_name": "Test User 2"
            }
        )
        if register_response.status_code == 201:
            print("User created successfully, logging in...")
            login_response = requests.post(
                f"{BASE_URL}/auth/login",
                data={"username": "test2@fintellic.com", "password": "Test123456"}
            )
        else:
            print(f"Failed to create user: {register_response.text}")
            return
    
    if login_response.status_code != 200:
        print("Still can't login")
        return
        
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Login successful")
    
    # Check user tier
    print("\n3. Checking user info...")
    user_response = requests.get(f"{BASE_URL}/users/me", headers=headers)
    if user_response.status_code == 200:
        user_data = user_response.json()
        print(f"User: {user_data.get('email')}")
        print(f"Tier: {user_data.get('tier', 'unknown')}")
    
    # Get initial view stats
    print("\n4. Getting initial view stats...")
    stats_response = requests.get(f"{BASE_URL}/users/me/view-stats", headers=headers)
    if stats_response.status_code == 200:
        print(json.dumps(stats_response.json(), indent=2))
    else:
        print(f"View stats endpoint not working: {stats_response.status_code}")
    
    # Test viewing filings
    print("\n5. Testing filing views (Free users should be limited to 3)...")
    
    for i, filing_id in enumerate(filing_ids[:5]):  # Try to view 5 filings
        print(f"\n--- Attempt {i+1}: Viewing filing ID {filing_id} ---")
        
        # Try to view filing
        filing_response = requests.get(
            f"{BASE_URL}/filings/{filing_id}",
            headers=headers
        )
        
        if filing_response.status_code == 200:
            filing_data = filing_response.json()
            print(f"✅ Successfully viewed filing {filing_id}")
            
            # Show view limit info if present
            if "view_limit_info" in filing_data:
                info = filing_data["view_limit_info"]
                print(f"   Views today: {info.get('views_today', 'unknown')}")
                print(f"   Views remaining: {info.get('views_remaining', 'unknown')}")
                print(f"   Is Pro: {info.get('is_pro', False)}")
            
            # Show filing summary
            print(f"   Company: {filing_data.get('company', {}).get('name', 'Unknown')}")
            print(f"   Type: {filing_data.get('form_type', 'Unknown')}")
            
        elif filing_response.status_code == 403:
            print(f"❌ Access denied - Daily limit reached!")
            error_detail = filing_response.json().get("detail", {})
            if isinstance(error_detail, dict):
                print(f"   Message: {error_detail.get('message', 'Unknown error')}")
                print(f"   Views today: {error_detail.get('views_today', 'unknown')}")
                print(f"   Daily limit: {error_detail.get('daily_limit', 'unknown')}")
                print(f"   Upgrade URL: {error_detail.get('upgrade_url', 'unknown')}")
            else:
                print(f"   Error: {error_detail}")
                
        else:
            print(f"❌ Error {filing_response.status_code}: {filing_response.text[:200]}")
        
        # Small delay between requests
        time.sleep(0.5)
    
    # Final stats check
    print("\n6. Final view stats...")
    final_stats = requests.get(f"{BASE_URL}/users/me/view-stats", headers=headers)
    if final_stats.status_code == 200:
        print(json.dumps(final_stats.json(), indent=2))

if __name__ == "__main__":
    test_view_limits()
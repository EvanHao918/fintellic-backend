#!/usr/bin/env python3
"""
Test script for Free user view limits
"""
import requests
import json
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
FREE_USER_EMAIL = "test2@fintellic.com"
FREE_USER_PASSWORD = "Test123456"
PRO_USER_EMAIL = "test2@fintellic.com"
PRO_USER_PASSWORD = "Test123456"


def login(email, password):
    """Login and get access token"""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": email, "password": password}
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        print(f"Login failed for {email}: {response.text}")
        return None


def get_headers(token):
    """Get headers with auth token"""
    return {"Authorization": f"Bearer {token}"}


def test_view_stats(token):
    """Test viewing stats endpoint"""
    response = requests.get(
        f"{BASE_URL}/users/me/view-stats",
        headers=get_headers(token)
    )
    print("View Stats:", json.dumps(response.json(), indent=2))
    return response.json()


def test_view_filing(token, filing_id):
    """Test viewing a filing"""
    response = requests.get(
        f"{BASE_URL}/filings/{filing_id}",
        headers=get_headers(token)
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Successfully viewed filing {filing_id}")
        if "view_limit_info" in data:
            print(f"   Views remaining: {data['view_limit_info']['views_remaining']}")
            print(f"   Views today: {data['view_limit_info']['views_today']}")
    else:
        print(f"❌ Failed to view filing {filing_id}: {response.status_code}")
        print(f"   Response: {response.text}")
    
    return response


def test_check_access(token, filing_id):
    """Test check access endpoint"""
    response = requests.get(
        f"{BASE_URL}/filings/check-access/{filing_id}",
        headers=get_headers(token)
    )
    print(f"Check Access for filing {filing_id}:", json.dumps(response.json(), indent=2))
    return response.json()


def main():
    print("=== Testing Free User View Limits ===\n")
    
    # Test with Free user
    print("1. Testing with FREE user...")
    free_token = login(FREE_USER_EMAIL, FREE_USER_PASSWORD)
    if not free_token:
        print("Failed to login as free user. Creating one...")
        # Create free user
        requests.post(f"{BASE_URL}/auth/register", json={
            "email": FREE_USER_EMAIL,
            "password": FREE_USER_PASSWORD,
            "username": "freeuser"
        })
        free_token = login(FREE_USER_EMAIL, FREE_USER_PASSWORD)
    
    if free_token:
        print("\n2. Getting initial view stats...")
        test_view_stats(free_token)
        
        print("\n3. Viewing filings (testing limit)...")
        for i in range(5):  # Try to view 5 filings (should fail after 3)
            filing_id = i + 1
            print(f"\nAttempt {i+1}: Viewing filing {filing_id}")
            test_check_access(free_token, filing_id)
            test_view_filing(free_token, filing_id)
            test_view_stats(free_token)
    
    print("\n" + "="*50 + "\n")
    
    # Test with Pro user
    print("4. Testing with PRO user...")
    pro_token = login(PRO_USER_EMAIL, PRO_USER_PASSWORD)
    if not pro_token:
        print("Failed to login as pro user. You may need to create one manually.")
    else:
        print("\n5. Getting Pro user view stats...")
        test_view_stats(pro_token)
        
        print("\n6. Pro user viewing multiple filings...")
        for i in range(5):
            filing_id = i + 1
            print(f"\nViewing filing {filing_id}")
            test_view_filing(pro_token, filing_id)


if __name__ == "__main__":
    main()
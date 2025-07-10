#!/usr/bin/env python3
"""
Test script for watchlist functionality

Run: python scripts/test_watchlist.py
"""
import requests
import json
from typing import Dict
import sys
from colorama import init, Fore, Style

# Initialize colorama
init()

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
TEST_EMAIL = "test2@fintellic.com"
TEST_PASSWORD = "Test123456"

# Test companies
TEST_COMPANIES = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]


class WatchlistTester:
    def __init__(self):
        self.token = None
        self.headers = {}
        
    def login(self) -> bool:
        """Login and get access token"""
        print(f"\n{Fore.CYAN}Logging in...{Style.RESET_ALL}")
        
        response = requests.post(
            f"{BASE_URL}/auth/login",
            data={
                "username": TEST_EMAIL,
                "password": TEST_PASSWORD
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            self.token = data["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
            print(f"{Fore.GREEN}✓ Login successful{Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.RED}✗ Login failed: {response.text}{Style.RESET_ALL}")
            return False
    
    def test_search_companies(self):
        """Test company search functionality"""
        print(f"\n{Fore.CYAN}Testing company search...{Style.RESET_ALL}")
        
        # Test different search queries
        search_queries = ["APP", "Tesla", "micro", "NV"]
        
        for query in search_queries:
            response = requests.get(
                f"{BASE_URL}/watchlist/search",
                params={"q": query, "limit": 5},
                headers=self.headers
            )
            
            if response.status_code == 200:
                results = response.json()
                print(f"\n{Fore.YELLOW}Search '{query}':{Style.RESET_ALL}")
                for company in results[:3]:  # Show first 3 results
                    indices = ", ".join(company["indices"])
                    watched = "📌" if company["is_watchlisted"] else ""
                    print(f"  - {company['ticker']}: {company['name']} ({indices}) {watched}")
            else:
                print(f"{Fore.RED}✗ Search failed for '{query}': {response.text}{Style.RESET_ALL}")
    
    def test_add_to_watchlist(self):
        """Test adding companies to watchlist"""
        print(f"\n{Fore.CYAN}Testing add to watchlist...{Style.RESET_ALL}")
        
        for ticker in TEST_COMPANIES:
            response = requests.post(
                f"{BASE_URL}/watchlist/{ticker}",
                headers=self.headers
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"{Fore.GREEN}✓ Added {ticker}: {data['message']}{Style.RESET_ALL}")
            elif response.status_code == 400:
                print(f"{Fore.YELLOW}! {ticker} already in watchlist{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}✗ Failed to add {ticker}: {response.text}{Style.RESET_ALL}")
    
    def test_get_watchlist(self):
        """Test getting watchlist"""
        print(f"\n{Fore.CYAN}Testing get watchlist...{Style.RESET_ALL}")
        
        response = requests.get(
            f"{BASE_URL}/watchlist",
            headers=self.headers
        )
        
        if response.status_code == 200:
            watchlist = response.json()
            print(f"\n{Fore.GREEN}Watchlist ({len(watchlist)} companies):{Style.RESET_ALL}")
            
            for company in watchlist:
                indices = ", ".join(company["indices"])
                filing_info = ""
                if company.get("last_filing"):
                    filing = company["last_filing"]
                    filing_info = f" - Last: {filing['filing_type']} ({filing['filing_date'][:10]})"
                
                print(f"  - {company['ticker']}: {company['name']} ({indices}){filing_info}")
        else:
            print(f"{Fore.RED}✗ Failed to get watchlist: {response.text}{Style.RESET_ALL}")
    
    def test_check_status(self):
        """Test checking watchlist status"""
        print(f"\n{Fore.CYAN}Testing watchlist status check...{Style.RESET_ALL}")
        
        test_tickers = ["AAPL", "AMZN", "JPM"]
        
        for ticker in test_tickers:
            response = requests.get(
                f"{BASE_URL}/watchlist/check/{ticker}",
                headers=self.headers
            )
            
            if response.status_code == 200:
                data = response.json()
                status = "✓ Watched" if data["is_watchlisted"] else "✗ Not watched"
                print(f"  {ticker}: {status}")
            else:
                print(f"{Fore.RED}✗ Failed to check {ticker}: {response.text}{Style.RESET_ALL}")
    
    def test_remove_from_watchlist(self):
        """Test removing from watchlist"""
        print(f"\n{Fore.CYAN}Testing remove from watchlist...{Style.RESET_ALL}")
        
        # Remove one company
        ticker = TEST_COMPANIES[0]
        response = requests.delete(
            f"{BASE_URL}/watchlist/{ticker}",
            headers=self.headers
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"{Fore.GREEN}✓ Removed {ticker}: {data['message']}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}✗ Failed to remove {ticker}: {response.text}{Style.RESET_ALL}")
    
    def test_watchlist_count(self):
        """Test getting watchlist count"""
        print(f"\n{Fore.CYAN}Testing watchlist count...{Style.RESET_ALL}")
        
        response = requests.get(
            f"{BASE_URL}/watchlist/count",
            headers=self.headers
        )
        
        if response.status_code == 200:
            data = response.json()
            limit_info = " (unlimited)" if data['limit'] is None else f"/{data['limit']}"
            pro_status = "Pro" if data['is_pro'] else "Free"
            print(f"  Count: {data['count']}{limit_info} ({pro_status} user)")
        else:
            print(f"{Fore.RED}✗ Failed to get count: {response.text}{Style.RESET_ALL}")
    
    def run_all_tests(self):
        """Run all tests"""
        print(f"{Fore.CYAN}{'='*50}")
        print(f"Watchlist API Test Suite")
        print(f"{'='*50}{Style.RESET_ALL}")
        
        if not self.login():
            print(f"{Fore.RED}Cannot proceed without login{Style.RESET_ALL}")
            return
        
        # Run tests in sequence
        self.test_search_companies()
        self.test_add_to_watchlist()
        self.test_get_watchlist()
        self.test_check_status()
        self.test_watchlist_count()
        self.test_remove_from_watchlist()
        
        print(f"\n{Fore.GREEN}{'='*50}")
        print(f"All tests completed!")
        print(f"{'='*50}{Style.RESET_ALL}")


if __name__ == "__main__":
    tester = WatchlistTester()
    tester.run_all_tests()
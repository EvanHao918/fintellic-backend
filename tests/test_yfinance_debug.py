# test_yfinance_debug.py
"""
Debug yfinance issues
"""
import sys
print("Python version:", sys.version)

# Test lxml import
try:
    import lxml
    print("✓ lxml version:", lxml.__version__)
    import lxml.html
    print("✓ lxml.html imported successfully")
except Exception as e:
    print("✗ lxml error:", e)

# Test other dependencies
try:
    import pandas
    print("✓ pandas version:", pandas.__version__)
except Exception as e:
    print("✗ pandas error:", e)

try:
    import numpy
    print("✓ numpy version:", numpy.__version__)
except Exception as e:
    print("✗ numpy error:", e)

# Test yfinance
try:
    import yfinance as yf
    print("✓ yfinance version:", yf.__version__)
    
    # Test basic functionality
    print("\nTesting yfinance basic functionality...")
    ticker = yf.Ticker("AAPL")
    info = ticker.info
    print(f"✓ Got ticker info for {info.get('longName', 'AAPL')}")
    
    # Test earnings dates specifically
    print("\nTesting earnings_dates...")
    try:
        # Try the old way
        earnings = ticker.calendar
        print("✓ Calendar data:", earnings)
    except Exception as e:
        print("✗ Calendar error:", e)
    
    # Try another approach
    print("\nTrying earnings_history...")
    try:
        earnings_hist = ticker.earnings_history
        print(f"✓ Got {len(earnings_hist)} historical earnings")
    except Exception as e:
        print("✗ Earnings history error:", e)
        
except Exception as e:
    print("✗ yfinance error:", e)
    import traceback
    traceback.print_exc()

# Alternative: Test with requests and pandas
print("\n\nTesting alternative approach with requests...")
try:
    import requests
    import pandas as pd
    
    # Test if we can get data directly
    url = "https://finance.yahoo.com/quote/AAPL"
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    print(f"✓ Got response from Yahoo Finance: {response.status_code}")
    
except Exception as e:
    print("✗ Alternative approach error:", e)
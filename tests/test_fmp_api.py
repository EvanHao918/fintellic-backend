#!/usr/bin/env python3
"""
Test FMP API connectivity and data
"""
import asyncio
import sys
from pathlib import Path
from datetime import date, timedelta
import logging
import aiohttp

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.fmp_service import fmp_service
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_basic_api():
    """Test basic FMP API access"""
    api_key = settings.FMP_API_KEY
    
    # Test different endpoints to see what works
    test_endpoints = [
        # Basic company profile (usually works with free tier)
        f"https://financialmodelingprep.com/api/v3/profile/AAPL?apikey={api_key}",
        
        # Quote endpoint (should work with free tier)
        f"https://financialmodelingprep.com/api/v3/quote/AAPL?apikey={api_key}",
        
        # Earnings calendar (might require paid tier)
        f"https://financialmodelingprep.com/api/v3/earning_calendar?from=2025-08-02&to=2025-08-10&apikey={api_key}",
        
        # Analyst estimates (might require paid tier)
        f"https://financialmodelingprep.com/api/v3/analyst-estimates/AAPL?apikey={api_key}",
    ]
    
    async with aiohttp.ClientSession() as session:
        for url in test_endpoints:
            endpoint = url.split('?')[0].split('/api/v3/')[-1]
            logger.info(f"\nTesting endpoint: {endpoint}")
            
            try:
                async with session.get(url, timeout=10) as response:
                    logger.info(f"Status: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, list):
                            logger.info(f"✅ Success! Got {len(data)} items")
                        else:
                            logger.info(f"✅ Success! Got data: {list(data.keys())[:5]}...")
                    elif response.status == 403:
                        text = await response.text()
                        logger.error(f"❌ 403 Forbidden - {text}")
                    else:
                        text = await response.text()
                        logger.error(f"❌ Error {response.status}: {text}")
                        
            except Exception as e:
                logger.error(f"❌ Exception: {e}")


async def test_fmp_connection():
    """Test FMP API connection and earnings calendar"""
    logger.info("Testing FMP API connection...")
    logger.info(f"API Key configured: {'Yes' if settings.FMP_API_KEY else 'No'}")
    logger.info(f"API Key (first 8 chars): {settings.FMP_API_KEY[:8] if settings.FMP_API_KEY else 'NOT SET'}...")
    
    # First test basic API access
    await test_basic_api()
    
    # Test our service methods
    logger.info("\n" + "="*50)
    logger.info("Testing FMP Service methods...")
    
    # Test 1: Get analyst estimates for a single company
    logger.info("\n1. Testing analyst estimates for AAPL...")
    try:
        estimates = await fmp_service.get_analyst_estimates("AAPL")
        if estimates:
            logger.info(f"✅ Got estimates: {estimates}")
        else:
            logger.warning("❌ No estimates returned")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
    
    # Test 2: Get earnings calendar
    logger.info("\n2. Testing earnings calendar...")
    try:
        start_date = date.today()
        end_date = start_date + timedelta(days=30)
        
        logger.info(f"Fetching earnings from {start_date} to {end_date}")
        earnings = await fmp_service.get_earnings_calendar(
            start_date.isoformat(),
            end_date.isoformat()
        )
        
        if earnings:
            logger.info(f"✅ Got {len(earnings)} earnings entries")
            # Show first few entries
            for i, entry in enumerate(earnings[:3]):
                logger.info(f"  - {entry.get('symbol')}: {entry.get('date')} ({entry.get('time')})")
            if len(earnings) > 3:
                logger.info(f"  ... and {len(earnings) - 3} more")
        else:
            logger.warning("❌ No earnings data returned")
            
    except Exception as e:
        logger.error(f"❌ Error: {e}")
    
    # Close session
    await fmp_service.close()
    logger.info("\n✅ Session closed properly")


if __name__ == "__main__":
    asyncio.run(test_fmp_connection())
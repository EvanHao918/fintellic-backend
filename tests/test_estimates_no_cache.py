#!/usr/bin/env python3
"""
Test analyst estimates without cache
"""
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.services.fmp_service import fmp_service
from app.core.cache import cache
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_estimates():
    """Test analyst estimates for major companies"""
    test_tickers = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA']
    
    logger.info("Testing analyst estimates with upgraded FMP API (cache cleared)...")
    
    # Clear cache for all test tickers
    for ticker in test_tickers:
        cache_key = f"fmp_estimates:{ticker}"
        cache.delete(cache_key)
        logger.info(f"Cleared cache for {ticker}")
    
    for ticker in test_tickers:
        logger.info(f"\nTesting {ticker}:")
        try:
            # First, let's see what the earnings calendar returns
            calendar_data = await fmp_service._make_request(f"/historical/earning_calendar/{ticker}?limit=5")
            if calendar_data:
                logger.info(f"  Earnings calendar data:")
                for event in calendar_data[:2]:
                    logger.info(f"    {event.get('date')}: EPS Est=${event.get('epsEstimated')}, Rev Est=${event.get('revenueEstimated', 0)/1e9 if event.get('revenueEstimated') else 'N/A'}B")
            
            # Now test the service method
            estimates = await fmp_service.get_analyst_estimates(ticker)
            if estimates:
                logger.info(f"  ✅ Revenue Estimate: ${estimates['revenue_estimate']['value']}B")
                logger.info(f"  ✅ EPS Estimate: ${estimates['eps_estimate']['value']}")
                logger.info(f"  ✅ Data Source: {estimates.get('data_source', 'unknown')}")
                logger.info(f"  ✅ Period Type: {estimates.get('period_type', 'unknown')}")
                logger.info(f"  ✅ Period: {estimates.get('period', 'unknown')}")
                if 'note' in estimates:
                    logger.info(f"  ⚠️  Note: {estimates['note']}")
            else:
                logger.warning(f"  ❌ No estimates for {ticker}")
        except Exception as e:
            logger.error(f"  ❌ Error for {ticker}: {e}")
    
    await fmp_service.close()


if __name__ == "__main__":
    asyncio.run(test_estimates())
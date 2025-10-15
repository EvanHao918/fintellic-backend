#!/usr/bin/env python3
"""
Test analyst estimates functionality after upgrade
"""
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.services.fmp_service import fmp_service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_estimates():
    """Test analyst estimates for major companies"""
    test_tickers = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA']
    
    logger.info("Testing analyst estimates with upgraded FMP API...")
    
    for ticker in test_tickers:
        logger.info(f"\nTesting {ticker}:")
        try:
            estimates = await fmp_service.get_analyst_estimates(ticker)
            if estimates:
                logger.info(f"✅ Revenue Estimate: ${estimates['revenue_estimate']['value']}B")
                logger.info(f"✅ EPS Estimate: ${estimates['eps_estimate']['value']}")
                logger.info(f"✅ Analysts: {estimates['revenue_estimate']['analysts']}")
            else:
                logger.warning(f"❌ No estimates for {ticker}")
        except Exception as e:
            logger.error(f"❌ Error for {ticker}: {e}")
    
    await fmp_service.close()


if __name__ == "__main__":
    asyncio.run(test_estimates())
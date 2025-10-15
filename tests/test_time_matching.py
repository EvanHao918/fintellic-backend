#!/usr/bin/env python3
"""
Test time-based analyst estimates matching
Enhanced version to test the fixed date matching logic
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.append(str(Path(__file__).parent.parent))

from app.services.fmp_service import fmp_service
from app.core.cache import FMPCache, cache
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_time_matching():
    """Test analyst estimates time matching functionality"""
    
    # Enhanced test scenarios
    test_cases = [
        {
            "name": "Current quarter (no date)",
            "ticker": "AAPL",
            "target_date": None,
            "description": "Should get next upcoming estimate"
        },
        {
            "name": "Q2 2025 Period End (June 30)",
            "ticker": "AAPL",
            "target_date": "2025-06-30",
            "description": "Should match to Q2 2025 report date (July 31)"
        },
        {
            "name": "Q2 2025 Report Date (July 31)",
            "ticker": "AAPL", 
            "target_date": "2025-07-31",
            "description": "Should get Q2 2025 estimate directly"
        },
        {
            "name": "Q1 2025 Period End (March 31)",
            "ticker": "AAPL",
            "target_date": "2025-03-31",
            "description": "Should match to Q1 2025 report date (April/May)"
        },
        {
            "name": "Q3 2024 Period End (Sept 30)",
            "ticker": "AAPL",
            "target_date": "2024-09-30",
            "description": "Should match to Q3 2024 report date (October)"
        },
        {
            "name": "Q4 2024 Period End (Dec 31)",
            "ticker": "AAPL",
            "target_date": "2024-12-31",
            "description": "Should match to Q4 2024 report date (January 2025)"
        }
    ]
    
    logger.info("="*60)
    logger.info("Testing Enhanced Time-Based Analyst Estimates Matching")
    logger.info("="*60)
    
    successful_matches = 0
    total_tests = len(test_cases)
    
    for test in test_cases:
        logger.info(f"\n### Test: {test['name']}")
        logger.info(f"Description: {test['description']}")
        
        # Clear cache for clean test
        if test['target_date']:
            cache_key = FMPCache.get_analyst_estimates_key(test['ticker'], test['target_date'])
        else:
            cache_key = FMPCache.get_analyst_estimates_key(test['ticker'])
        cache.delete(cache_key)
        
        try:
            # Get estimates
            estimates = await fmp_service.get_analyst_estimates(
                test['ticker'],
                target_date=test['target_date']
            )
            
            if estimates:
                logger.info("✅ Success!")
                logger.info(f"   Period: {estimates['period']}")
                logger.info(f"   Revenue Est: ${estimates['revenue_estimate']['value']}B")
                logger.info(f"   EPS Est: ${estimates['eps_estimate']['value']}")
                logger.info(f"   Data Source: {estimates['data_source']}")
                
                # Check if the period matches expectation
                if test['target_date']:
                    target_dt = datetime.strptime(test['target_date'], '%Y-%m-%d')
                    period_dt = datetime.strptime(estimates['period'], '%Y-%m-%d')
                    diff_days = abs((target_dt - period_dt).days)
                    
                    # Enhanced matching validation
                    if target_dt.day >= 25:  # Period end date
                        # For period end dates, expect 0-45 days forward match
                        forward_diff = (period_dt - target_dt).days
                        if 0 <= forward_diff <= 45:
                            logger.info(f"   ✅ EXCELLENT period-end match! Report date {forward_diff} days after period end")
                            successful_matches += 1
                        else:
                            logger.warning(f"   ⚠️  Poor period-end match. Diff: {diff_days} days")
                    else:
                        # Regular date matching
                        if diff_days <= 10:
                            logger.info(f"   ✅ Excellent match! Only {diff_days} days difference")
                            successful_matches += 1
                        elif diff_days <= 30:
                            logger.info(f"   ✅ Good match! {diff_days} days difference")
                            successful_matches += 1
                        else:
                            logger.warning(f"   ⚠️  Poor match! {diff_days} days difference")
                else:
                    successful_matches += 1
            else:
                logger.warning("❌ No estimates found")
                
        except Exception as e:
            logger.error(f"❌ Error: {e}")
    
    # Test cache functionality
    logger.info("\n### Testing Cache")
    logger.info("Fetching AAPL with date 2025-06-30 again (should be cached)...")
    
    start_time = datetime.now()
    estimates = await fmp_service.get_analyst_estimates("AAPL", target_date="2025-06-30")
    elapsed = (datetime.now() - start_time).total_seconds()
    
    if elapsed < 0.1:
        logger.info(f"✅ Cache hit! Fetched in {elapsed:.3f} seconds")
    else:
        logger.info(f"⚠️  Seems like cache miss. Fetched in {elapsed:.3f} seconds")
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info(f"Test Summary: {successful_matches}/{total_tests} tests passed")
    logger.info("="*60)
    
    # Don't close session here, let the last test do it
    logger.info("\n✅ Basic tests completed!")


async def test_real_filing_scenarios():
    """Test with multiple real filing scenarios"""
    logger.info("\n" + "="*60)
    logger.info("Testing Real Filing Scenarios")
    logger.info("="*60)
    
    # Multiple realistic scenarios
    filing_scenarios = [
        {
            "name": "Apple Q2 2025",
            "ticker": "AAPL",
            "filing_date": "2025-07-31",
            "period_end_date": "2025-06-30",
            "filing_type": "10-Q"
        },
        {
            "name": "Microsoft Q1 2025",
            "ticker": "MSFT",
            "filing_date": "2025-04-25",
            "period_end_date": "2025-03-31",
            "filing_type": "10-Q"
        },
        {
            "name": "Google Q3 2024",
            "ticker": "GOOGL",
            "filing_date": "2024-10-29",
            "period_end_date": "2024-09-30",
            "filing_type": "10-Q"
        }
    ]
    
    successful_scenarios = 0
    
    for scenario in filing_scenarios:
        logger.info(f"\n### Scenario: {scenario['name']}")
        logger.info(f"Ticker: {scenario['ticker']}")
        logger.info(f"Filing Date: {scenario['filing_date']} (when released)")
        logger.info(f"Period End Date: {scenario['period_end_date']} (quarter end)")
        
        # This simulates what AI processor would do
        target_date = scenario['period_end_date']
        logger.info(f"\nFetching estimates for period ending {target_date}...")
        
        estimates = await fmp_service.get_analyst_estimates(
            scenario['ticker'],
            target_date=target_date
        )
        
        if estimates:
            logger.info("✅ Found estimates!")
            logger.info(f"   Estimate Period: {estimates['period']}")
            logger.info(f"   Revenue: ${estimates['revenue_estimate']['value']}B")
            logger.info(f"   EPS: ${estimates['eps_estimate']['value']}")
            
            # Validate the match
            estimate_date = datetime.strptime(estimates['period'], '%Y-%m-%d')
            period_date = datetime.strptime(scenario['period_end_date'], '%Y-%m-%d')
            filing_date = datetime.strptime(scenario['filing_date'], '%Y-%m-%d')
            
            # Check if estimate date is between period end and filing date (or close)
            days_from_period = (estimate_date - period_date).days
            days_from_filing = abs((estimate_date - filing_date).days)
            
            logger.info(f"   Days from period end: {days_from_period}")
            logger.info(f"   Days from filing date: {days_from_filing}")
            
            if 0 <= days_from_period <= 45 or days_from_filing <= 5:
                logger.info(f"   ✅ CORRECT MATCH! This is the right quarter's estimate")
                successful_scenarios += 1
            else:
                logger.warning(f"   ⚠️  WRONG MATCH! This might be comparing wrong quarters!")
        else:
            logger.error("❌ No estimates found - Beat/Miss analysis would fail")
    
    logger.info("\n" + "="*60)
    logger.info(f"Scenario Summary: {successful_scenarios}/{len(filing_scenarios)} successful")
    logger.info("="*60)


async def test_edge_cases():
    """Test edge cases and problematic dates"""
    logger.info("\n" + "="*60)
    logger.info("Testing Edge Cases")
    logger.info("="*60)
    
    edge_cases = [
        {
            "name": "Weekend period end",
            "ticker": "AAPL",
            "target_date": "2025-06-28",  # Saturday
            "description": "Period ending on weekend"
        },
        {
            "name": "Mid-month date",
            "ticker": "AAPL",
            "target_date": "2025-07-15",
            "description": "Mid-month date (not period end)"
        },
        {
            "name": "Very old date",
            "ticker": "AAPL",
            "target_date": "2023-12-31",
            "description": "Historical data from 2023"
        },
        {
            "name": "Future date",
            "ticker": "AAPL",
            "target_date": "2026-03-31",
            "description": "Far future date"
        }
    ]
    
    for test in edge_cases:
        logger.info(f"\n### Edge Case: {test['name']}")
        logger.info(f"Description: {test['description']}")
        logger.info(f"Target Date: {test['target_date']}")
        
        try:
            estimates = await fmp_service.get_analyst_estimates(
                test['ticker'],
                target_date=test['target_date']
            )
            
            if estimates:
                logger.info(f"✅ Found estimate for period: {estimates['period']}")
            else:
                logger.info("❌ No estimates found (this might be expected)")
                
        except Exception as e:
            logger.error(f"❌ Error: {e}")
    
    await fmp_service.close()


if __name__ == "__main__":
    # Run all test suites
    asyncio.run(test_time_matching())
    asyncio.run(test_real_filing_scenarios())
    asyncio.run(test_edge_cases())
    
    # Close session after all tests
    async def cleanup():
        await fmp_service.close()
        logger.info("\n✅ All test suites completed and cleaned up!")
    
    asyncio.run(cleanup())
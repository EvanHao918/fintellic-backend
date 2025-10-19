"""
Financial Modeling Prep API Service - OPTIMIZED FOR BEAT/MISS ANALYSIS
Handles all FMP API interactions with caching and error handling
OPTIMIZED: Simplified analyst estimates fetching for latest quarter
"""
import requests
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging
from app.core.config import settings
from app.core.cache import cache

logger = logging.getLogger(__name__)

class FMPService:
    def __init__(self):
        self.api_key = settings.FMP_API_KEY
        self.api_version = settings.FMP_API_VERSION or "v3"
        self.base_url = f"https://financialmodelingprep.com/api/{self.api_version}"
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """统一的请求处理"""
        if not self.api_key:
            logger.error("FMP API key not configured")
            return None
        
        url = f"{self.base_url}{endpoint}"
        params = params or {}
        params['apikey'] = self.api_key
        
        try:
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"FMP API error: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"FMP request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in FMP request: {e}")
            return None
    
    def get_company_profile(self, ticker: str) -> Optional[Dict]:
        """获取公司详细信息 - UNCHANGED"""
        cache_key = f"fmp:company_profile:{ticker}"
        cached = cache.get(cache_key)
        if cached:
            logger.info(f"[FMP] Using cached company profile for {ticker}")
            return json.loads(cached)
        
        profile_data = self._make_request(f"/profile/{ticker}")
        
        if profile_data and len(profile_data) > 0:
            profile = profile_data[0]
            
            result = {
                'ticker': profile.get('symbol'),
                'name': profile.get('companyName'),
                'legal_name': profile.get('companyName'),
                'sector': profile.get('sector'),
                'industry': profile.get('industry'),
                'exchange': profile.get('exchangeShortName'),
                'headquarters': f"{profile.get('city', '')}, {profile.get('state', '')}".strip(', ') if profile.get('city') or profile.get('state') else None,
                'country': profile.get('country'),
                'market_cap': profile.get('mktCap'),
                'pe_ratio': None,
                'website': profile.get('website'),
                'employees': profile.get('fullTimeEmployees'),
                'description': profile.get('description'),
                'ceo': profile.get('ceo'),
                'founded': profile.get('ipoDate'),
                'currency': profile.get('currency'),
                'price': profile.get('price'),
                'beta': profile.get('beta'),
                'volume_avg': profile.get('volAvg'),
                'market_cap_formatted': self._format_market_cap(profile.get('mktCap')),
                'fetch_timestamp': datetime.utcnow().isoformat(),
                'data_source': 'fmp_profile'
            }
            
            if profile.get('pe'):
                result['pe_ratio'] = profile.get('pe')
            
            result = {k: v for k, v in result.items() if v is not None}
            
            cache.set(cache_key, json.dumps(result), ttl=86400)
            logger.info(f"[FMP] Successfully fetched company profile for {ticker}")
            return result
        
        logger.warning(f"[FMP] No company profile found for {ticker}")
        return None
    
    def get_company_key_metrics(self, ticker: str) -> Optional[Dict]:
        """获取公司关键指标 - UNCHANGED"""
        cache_key = f"fmp:key_metrics:{ticker}"
        cached = cache.get(cache_key)
        if cached:
            logger.info(f"[FMP] Using cached key metrics for {ticker}")
            return json.loads(cached)
        
        metrics_data = self._make_request(f"/key-metrics/{ticker}?period=quarter&limit=1")
        
        if metrics_data and len(metrics_data) > 0:
            metrics = metrics_data[0]
            
            result = {
                'pe_ratio': metrics.get('peRatio'),
                'price_to_sales': metrics.get('priceToSalesRatio'),
                'price_to_book': metrics.get('pbRatio'),
                'revenue_per_share': metrics.get('revenuePerShare'),
                'net_income_per_share': metrics.get('netIncomePerShare'),
                'operating_cash_flow_per_share': metrics.get('operatingCashFlowPerShare'),
                'free_cash_flow_per_share': metrics.get('freeCashFlowPerShare'),
                'book_value_per_share': metrics.get('bookValuePerShare'),
                'debt_to_equity': metrics.get('debtToEquity'),
                'current_ratio': metrics.get('currentRatio'),
                'working_capital': metrics.get('workingCapital'),
                'return_on_equity': metrics.get('roe'),
                'return_on_assets': metrics.get('roa'),
                'gross_profit_margin': metrics.get('grossProfitMargin'),
                'operating_profit_margin': metrics.get('operatingProfitMargin'),
                'net_profit_margin': metrics.get('netProfitMargin'),
                'fetch_timestamp': datetime.utcnow().isoformat(),
                'data_source': 'fmp_key_metrics'
            }
            
            result = {k: v for k, v in result.items() if v is not None}
            
            cache.set(cache_key, json.dumps(result), ttl=3600)
            logger.info(f"[FMP] Successfully fetched key metrics for {ticker}")
            return result
        
        logger.warning(f"[FMP] No key metrics found for {ticker}")
        return None
    
    def _format_market_cap(self, market_cap: float) -> str:
        """Format market cap for display - UNCHANGED"""
        if not market_cap:
            return None
            
        if market_cap >= 1e12:
            return f"${market_cap / 1e12:.2f}T"
        elif market_cap >= 1e9:
            return f"${market_cap / 1e9:.2f}B"
        elif market_cap >= 1e6:
            return f"${market_cap / 1e6:.2f}M"
        else:
            return f"${market_cap:,.0f}"
    
    # ✅ NEW: Optimized method for beat/miss analysis
    def get_latest_analyst_estimates(self, ticker: str) -> Optional[Dict]:
        """
        获取最新季度的分析师预期 - OPTIMIZED FOR BEAT/MISS
        
        DESIGN LOGIC:
        - We process filings within 2 minutes of SEC release
        - At T+2min, the "latest" estimate in FMP = consensus for the just-reported quarter
        - Simply grab the most recent estimate, no complex date matching needed
        
        Args:
            ticker: Stock ticker
            
        Returns:
            Dict with {'eps': float, 'revenue': float, 'date': str} or None
        """
        cache_key = f"fmp:latest_estimates:{ticker}"
        cached = cache.get(cache_key)
        if cached:
            logger.info(f"[FMP] Using cached latest estimates for {ticker}")
            return json.loads(cached)
        
        # Fetch recent earnings calendar (limit=5 to get last few quarters)
        calendar_data = self._make_request(f"/historical/earning_calendar/{ticker}?limit=5")
        
        if not calendar_data or len(calendar_data) == 0:
            logger.warning(f"[FMP] No earnings calendar data for {ticker}")
            return None
        
        current_date = datetime.now().date()
        
        # STRATEGY: Find the most recent earnings date that has estimates
        # This will be either:
        # 1. Today's earnings (if filing just released)
        # 2. Most recent past earnings (within last 45 days)
        
        best_match = None
        min_days_ago = float('inf')
        
        for event in calendar_data:
            if not event.get('date'):
                continue
            
            # Check if estimates exist
            eps_est = event.get('epsEstimated')
            revenue_est = event.get('revenueEstimated')
            
            if eps_est is None and revenue_est is None:
                continue
            
            try:
                event_date = datetime.strptime(event.get('date'), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                continue
            
            # Calculate days difference
            days_diff = (current_date - event_date).days
            
            # Accept if:
            # - Within last 45 days (recent quarter)
            # - Or future (today's earnings announcement)
            if -1 <= days_diff <= 45:  # -1 allows for same-day or next-day
                if days_diff < min_days_ago:
                    best_match = event
                    min_days_ago = days_diff
                    logger.info(f"[FMP] Found estimate for {ticker} dated {event_date} ({days_diff} days ago)")
        
        if best_match:
            result = {
                'eps': best_match.get('epsEstimated'),
                'revenue': best_match.get('revenueEstimated') / 1e9 if best_match.get('revenueEstimated') else None,  # Convert to billions
                'date': best_match.get('date'),
                'fetch_timestamp': datetime.utcnow().isoformat(),
                'data_source': 'fmp_earnings_calendar'
            }
            
            # Cache for 1 hour (estimates don't change frequently)
            cache.set(cache_key, json.dumps(result), ttl=3600)
            
            logger.info(
                f"[FMP] Latest estimates for {ticker}: "
                f"EPS=${result['eps']}, Revenue=${result['revenue']}B, Date={result['date']}"
            )
            
            return result
        
        logger.warning(f"[FMP] No recent estimates found for {ticker}")
        return None
    
    # ✅ KEEP: Original method for backward compatibility and complex use cases
    def get_analyst_estimates(self, ticker: str, target_date: Optional[str] = None) -> Optional[Dict]:
        """
        获取分析师预期 - 支持指定日期的预期获取
        LEGACY METHOD: Kept for backward compatibility
        
        For beat/miss analysis, use get_latest_analyst_estimates() instead
        """
        from app.core.cache import FMPCache
        cache_key = FMPCache.get_analyst_estimates_key(ticker, target_date)
        cached = cache.get(cache_key)
        if cached:
            logger.info(f"[FMP] Using cached analyst estimates for {ticker}")
            return json.loads(cached)
        
        calendar_data = self._make_request(f"/historical/earning_calendar/{ticker}?limit=40")
        
        if calendar_data and len(calendar_data) > 0:
            current_date = datetime.now().date()
            selected_estimate = None
            
            if target_date:
                target_dt = datetime.strptime(target_date, '%Y-%m-%d').date()
                
                best_match = None
                min_diff = float('inf')
                
                for event in calendar_data:
                    if not event.get('date'):
                        continue
                        
                    event_date = datetime.strptime(event.get('date', ''), '%Y-%m-%d').date()
                    diff = (event_date - target_dt).days
                    
                    if target_dt.day >= 25:
                        if 0 <= diff <= 45 and abs(diff) < min_diff:
                            if event.get('epsEstimated') is not None or event.get('revenueEstimated') is not None:
                                best_match = event
                                min_diff = abs(diff)
                                logger.info(f"[FMP] Found potential match for period end {target_date}: {event['date']} (diff: {diff} days)")
                    
                    elif abs(diff) <= 30 and abs(diff) < min_diff:
                        if event.get('epsEstimated') is not None or event.get('revenueEstimated') is not None:
                            best_match = event
                            min_diff = abs(diff)
                
                if best_match:
                    selected_estimate = best_match
                    logger.info(f"[FMP] Using estimate for {ticker} near {target_date}: {best_match['date']} (diff: {min_diff} days)")
                else:
                    for event in calendar_data:
                        if not event.get('date'):
                            continue
                            
                        event_date = datetime.strptime(event.get('date', ''), '%Y-%m-%d').date()
                        diff = abs((event_date - target_dt).days)
                        
                        if diff <= 60 and diff < min_diff:
                            if event.get('epsEstimated') is not None or event.get('revenueEstimated') is not None:
                                best_match = event
                                min_diff = diff
                    
                    if best_match:
                        selected_estimate = best_match
                        logger.warning(f"[FMP] Using wider match for {ticker} near {target_date}: {best_match['date']} (diff: {min_diff} days)")
                    else:
                        logger.warning(f"[FMP] No estimate found for {ticker} near {target_date}")
            
            else:
                for event in calendar_data:
                    if not event.get('date'):
                        continue
                        
                    event_date = datetime.strptime(event.get('date', ''), '%Y-%m-%d').date()
                    
                    if event_date >= current_date and (event.get('epsEstimated') is not None or event.get('revenueEstimated') is not None):
                        selected_estimate = event
                        break
            
            if selected_estimate:
                logger.info(f"[FMP] Using estimate for {ticker} on {selected_estimate['date']}")
                
                result = {
                    'revenue_estimate': {
                        'value': selected_estimate.get('revenueEstimated', 0) / 1e9 if selected_estimate.get('revenueEstimated') else None,
                        'analysts': 0
                    },
                    'eps_estimate': {
                        'value': selected_estimate.get('epsEstimated'),
                        'analysts': 0
                    },
                    'period': selected_estimate.get('date'),
                    'period_type': 'quarterly',
                    'fetch_timestamp': datetime.utcnow().isoformat(),
                    'data_source': 'fmp_quarterly'
                }
                
                cache.set(cache_key, json.dumps(result), ttl=settings.FMP_CACHE_TTL)
                return result
        
        annual_data = self._make_request(f"/analyst-estimates/{ticker}")
        
        if annual_data and len(annual_data) > 0:
            latest = annual_data[0]
            
            result = {
                'revenue_estimate': {
                    'value': latest.get('estimatedRevenueAvg', 0) / 1e9 / 4,
                    'analysts': latest.get('numberAnalystsEstimatedRevenue', 0)
                },
                'eps_estimate': {
                    'value': latest.get('estimatedEpsAvg', 0) / 4,
                    'analysts': latest.get('numberAnalystsEstimatedEps', 0)
                },
                'period': latest.get('date'),
                'period_type': 'annual_divided_by_4',
                'note': 'Quarterly estimate derived from annual data',
                'fetch_timestamp': datetime.utcnow().isoformat(),
                'data_source': 'fmp_annual_adjusted'
            }
            
            logger.warning(f"[FMP] Using annual estimates divided by 4 for {ticker}")
            cache.set(cache_key, json.dumps(result), ttl=settings.FMP_CACHE_TTL)
            return result
        
        logger.info(f"[FMP] No analyst estimates found for {ticker}")
        return None
    
    def get_earnings_calendar(self, from_date: str, to_date: str) -> List[Dict]:
        """获取财报日历 - UNCHANGED"""
        from app.core.cache import FMPCache
        cache_key = FMPCache.get_earnings_calendar_key(from_date, to_date)
        cached = cache.get(cache_key)
        if cached:
            return json.loads(cached)
        
        params = {"from": from_date, "to": to_date}
        data = self._make_request("/earning_calendar", params)
        
        if data:
            logger.info(f"[FMP] Retrieved {len(data)} earnings entries for {from_date} to {to_date}")
            cache.set(cache_key, json.dumps(data), ttl=3600)
            return data
        else:
            logger.warning(f"[FMP] No earnings calendar data for {from_date} to {to_date}")
        
        return []

# 单例
fmp_service = FMPService()
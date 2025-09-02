"""
Financial Modeling Prep API Service - ENHANCED VERSION
Handles all FMP API interactions with caching and error handling
FIXED: Changed from async to sync to resolve "Event loop is closed" error
ENHANCED: Improved date matching logic for analyst estimates
ENHANCED: Added company profile fetching capability
UPDATED: Enhanced for FMP API optimization project - better data structure for database storage
"""
import requests  # Changed from aiohttp to requests for sync operations
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
        """统一的请求处理 - CHANGED TO SYNC"""
        if not self.api_key:
            logger.error("FMP API key not configured")
            return None
        
        url = f"{self.base_url}{endpoint}"
        params = params or {}
        params['apikey'] = self.api_key
        
        try:
            # FIXED: Using requests instead of aiohttp for sync operation
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
        """
        获取公司详细信息
        ENHANCED: Enhanced for database integration - returns structured data for Company model
        UPDATED: Improved data mapping for FMP API optimization project
        
        Args:
            ticker: 股票代码 
            
        Returns:
            Dict with company information optimized for database storage or None
        """
        # Generate cache key
        cache_key = f"fmp:company_profile:{ticker}"
        cached = cache.get(cache_key)
        if cached:
            logger.info(f"[FMP] Using cached company profile for {ticker}")
            return json.loads(cached)
        
        # Fetch company profile
        profile_data = self._make_request(f"/profile/{ticker}")
        
        if profile_data and len(profile_data) > 0:
            profile = profile_data[0]  # API returns array with single item
            
            # UPDATED: Enhanced data mapping for database integration
            result = {
                # Core identifiers
                'ticker': profile.get('symbol'),
                'name': profile.get('companyName'),
                'legal_name': profile.get('companyName'),
                
                # Business classification
                'sector': profile.get('sector'),
                'industry': profile.get('industry'),
                'exchange': profile.get('exchangeShortName'),
                
                # Location information
                'headquarters': f"{profile.get('city', '')}, {profile.get('state', '')}".strip(', ') if profile.get('city') or profile.get('state') else None,
                'country': profile.get('country'),
                
                # Key financial metrics - OPTIMIZED FOR DATABASE STORAGE
                'market_cap': profile.get('mktCap'),  # Raw value in USD
                'pe_ratio': None,  # Will be filled by key metrics call
                'website': profile.get('website'),
                
                # Additional company data
                'employees': profile.get('fullTimeEmployees'),
                'description': profile.get('description'),
                'ceo': profile.get('ceo'),
                'founded': profile.get('ipoDate'),  # IPO date as proxy for founding
                
                # Market data (for reference, not stored in DB)
                'currency': profile.get('currency'),
                'price': profile.get('price'),
                'beta': profile.get('beta'),
                'volume_avg': profile.get('volAvg'),
                
                # Formatted display values (for immediate use)
                'market_cap_formatted': self._format_market_cap(profile.get('mktCap')),
                
                # Metadata
                'fetch_timestamp': datetime.utcnow().isoformat(),
                'data_source': 'fmp_profile'
            }
            
            # ENHANCED: Try to get PE ratio from this profile call
            if profile.get('pe'):
                result['pe_ratio'] = profile.get('pe')
            
            # Remove None values to keep the result clean
            result = {k: v for k, v in result.items() if v is not None}
            
            # Cache for 24 hours (company profiles don't change often)
            cache.set(cache_key, json.dumps(result), ttl=86400)
            logger.info(f"[FMP] Successfully fetched company profile for {ticker}")
            return result
        
        logger.warning(f"[FMP] No company profile found for {ticker}")
        return None
    
    def get_company_key_metrics(self, ticker: str) -> Optional[Dict]:
        """
        获取公司关键指标
        ENHANCED: Enhanced for PE ratio fetching in FMP optimization project
        
        Args:
            ticker: 股票代码 
            
        Returns:
            Dict with key metrics including PE ratio or None
        """
        cache_key = f"fmp:key_metrics:{ticker}"
        cached = cache.get(cache_key)
        if cached:
            logger.info(f"[FMP] Using cached key metrics for {ticker}")
            return json.loads(cached)
        
        # Fetch key metrics (quarterly)
        metrics_data = self._make_request(f"/key-metrics/{ticker}?period=quarter&limit=1")
        
        if metrics_data and len(metrics_data) > 0:
            metrics = metrics_data[0]
            
            result = {
                # Core valuation metrics
                'pe_ratio': metrics.get('peRatio'),
                'price_to_sales': metrics.get('priceToSalesRatio'),
                'price_to_book': metrics.get('pbRatio'),
                
                # Per-share metrics
                'revenue_per_share': metrics.get('revenuePerShare'),
                'net_income_per_share': metrics.get('netIncomePerShare'),
                'operating_cash_flow_per_share': metrics.get('operatingCashFlowPerShare'),
                'free_cash_flow_per_share': metrics.get('freeCashFlowPerShare'),
                'book_value_per_share': metrics.get('bookValuePerShare'),
                
                # Financial health metrics
                'debt_to_equity': metrics.get('debtToEquity'),
                'current_ratio': metrics.get('currentRatio'),
                'working_capital': metrics.get('workingCapital'),
                
                # Profitability metrics
                'return_on_equity': metrics.get('roe'),
                'return_on_assets': metrics.get('roa'),
                'gross_profit_margin': metrics.get('grossProfitMargin'),
                'operating_profit_margin': metrics.get('operatingProfitMargin'),
                'net_profit_margin': metrics.get('netProfitMargin'),
                
                # Metadata
                'fetch_timestamp': datetime.utcnow().isoformat(),
                'data_source': 'fmp_key_metrics'
            }
            
            # Remove None values
            result = {k: v for k, v in result.items() if v is not None}
            
            # Cache for 1 hour (metrics change more frequently)
            cache.set(cache_key, json.dumps(result), ttl=3600)
            logger.info(f"[FMP] Successfully fetched key metrics for {ticker}")
            return result
        
        logger.warning(f"[FMP] No key metrics found for {ticker}")
        return None
    
    def _format_market_cap(self, market_cap: float) -> str:
        """Format market cap for display"""
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
    
    def get_analyst_estimates(self, ticker: str, target_date: Optional[str] = None) -> Optional[Dict]:
        """
        获取分析师预期 - 支持指定日期的预期获取
        FIXED: Changed from async to sync
        ENHANCED: 改进了日期匹配逻辑，支持期间结束日期到报告日期的映射
        
        Args:
            ticker: 股票代码 
            target_date: 目标日期（格式：YYYY-MM-DD），用于获取特定财报期的预期
                        如果不提供，则获取下一个即将到来的预期
        """
        # 使用新的缓存键生成方法
        from app.core.cache import FMPCache
        cache_key = FMPCache.get_analyst_estimates_key(ticker, target_date)
        cached = cache.get(cache_key)
        if cached:
            logger.info(f"[FMP] Using cached analyst estimates for {ticker}")
            return json.loads(cached)
        
        # Try to get quarterly estimates from earnings calendar
        calendar_data = self._make_request(f"/historical/earning_calendar/{ticker}?limit=40")
        
        if calendar_data and len(calendar_data) > 0:
            current_date = datetime.now().date()
            selected_estimate = None
            
            if target_date:
                # 如果指定了目标日期，找最接近的财报期
                target_dt = datetime.strptime(target_date, '%Y-%m-%d').date()
                
                # ENHANCED: 智能日期匹配逻辑
                # 对于期间结束日期（如6月30日），需要找到对应的报告日期（通常在下个月）
                best_match = None
                min_diff = float('inf')
                
                # 首先尝试找到同一季度的财报（考虑财报通常在季度结束后1-45天发布）
                for event in calendar_data:
                    if not event.get('date'):
                        continue
                        
                    event_date = datetime.strptime(event.get('date', ''), '%Y-%m-%d').date()
                    
                    # 计算日期差异
                    diff = (event_date - target_dt).days
                    
                    # 智能匹配逻辑：
                    # 1. 如果目标日期是月末（25-31号），可能是期间结束日期
                    # 2. 财报通常在期间结束后的15-45天内发布
                    if target_dt.day >= 25:  # 可能是期间结束日期
                        # 查找未来0-45天内的财报
                        if 0 <= diff <= 45 and abs(diff) < min_diff:
                            if event.get('epsEstimated') is not None or event.get('revenueEstimated') is not None:
                                best_match = event
                                min_diff = abs(diff)
                                logger.info(f"[FMP] Found potential match for period end {target_date}: {event['date']} (diff: {diff} days)")
                    
                    # 标准匹配：前后30天内
                    elif abs(diff) <= 30 and abs(diff) < min_diff:
                        if event.get('epsEstimated') is not None or event.get('revenueEstimated') is not None:
                            best_match = event
                            min_diff = abs(diff)
                
                if best_match:
                    selected_estimate = best_match
                    logger.info(f"[FMP] Using estimate for {ticker} near {target_date}: {best_match['date']} (diff: {min_diff} days)")
                else:
                    # 如果没找到，尝试更宽松的匹配（前后60天）
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
                # 原逻辑：找下一个即将到来的预期
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
                        'analysts': 0  # Not available in this endpoint
                    },
                    'eps_estimate': {
                        'value': selected_estimate.get('epsEstimated'),
                        'analysts': 0  # Not available in this endpoint
                    },
                    'period': selected_estimate.get('date'),
                    'period_type': 'quarterly',
                    'fetch_timestamp': datetime.utcnow().isoformat(),
                    'data_source': 'fmp_quarterly'
                }
                
                cache.set(cache_key, json.dumps(result), ttl=settings.FMP_CACHE_TTL)
                return result
        
        # Fallback to annual estimates if no quarterly found
        annual_data = self._make_request(f"/analyst-estimates/{ticker}")
        
        if annual_data and len(annual_data) > 0:
            # Get the most recent annual estimate
            latest = annual_data[0]
            
            # Convert annual to quarterly estimate (rough approximation)
            result = {
                'revenue_estimate': {
                    'value': latest.get('estimatedRevenueAvg', 0) / 1e9 / 4,  # Divide by 4 for quarterly
                    'analysts': latest.get('numberAnalystsEstimatedRevenue', 0)
                },
                'eps_estimate': {
                    'value': latest.get('estimatedEpsAvg', 0) / 4,  # Divide by 4 for quarterly
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
        """获取财报日历 - FIXED: Changed from async to sync"""
        # 使用新的缓存键生成方法
        from app.core.cache import FMPCache
        cache_key = FMPCache.get_earnings_calendar_key(from_date, to_date)
        cached = cache.get(cache_key)
        if cached:
            return json.loads(cached)
        
        params = {"from": from_date, "to": to_date}
        data = self._make_request("/earning_calendar", params)
        
        if data:
            # Log the data for debugging
            logger.info(f"[FMP] Retrieved {len(data)} earnings entries for {from_date} to {to_date}")
            cache.set(cache_key, json.dumps(data), ttl=3600)  # 1 小时缓存
            return data
        else:
            logger.warning(f"[FMP] No earnings calendar data for {from_date} to {to_date}")
        
        return []

# 单例
fmp_service = FMPService()
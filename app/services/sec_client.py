import httpx
import asyncio
import feedparser
import re
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class SECClient:
    """
    Client for interacting with SEC EDGAR API and RSS feeds
    Optimized for production use with RSS as primary discovery method
    """
    
    def __init__(self):
        self.base_url = "https://data.sec.gov"
        self.headers = {
            "User-Agent": settings.SEC_USER_AGENT,
            "Accept": "application/json",
            "Host": "data.sec.gov"
        }
        # Rate limiting: 10 requests per second
        self.rate_limit_delay = 0.1  # 100ms between requests
        self.last_request_time = datetime.min
        
    async def _rate_limit(self):
        """Ensure we don't exceed SEC rate limits"""
        now = datetime.now()
        time_since_last = (now - self.last_request_time).total_seconds()
        
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)
        
        self.last_request_time = datetime.now()
    
    async def get_rss_filings(self, form_type: str = "all", lookback_minutes: int = 60) -> List[Dict]:
        """
        Get filings from SEC RSS feed - PRIMARY method for discovering new filings
        
        Args:
            form_type: "all", "10-K", "10-Q", "8-K", or "S-1"
            lookback_minutes: How many minutes to look back (for filtering)
            
        Returns:
            List of recent filings from RSS
        """
        # Build RSS URL - filter for company filings only
        base_rss_url = "https://www.sec.gov/cgi-bin/browse-edgar"
        params = {
            "action": "getcurrent",
            "owner": "exclude",  # Exclude individual ownership reports
            "output": "atom",
            "count": "100",
            "start": "0"
        }
        
        # If looking for specific forms, be more targeted
        if form_type == "10-K":
            params["type"] = "10-K"
        elif form_type == "10-Q":
            params["type"] = "10-Q"
        elif form_type == "8-K":
            params["type"] = "8-K"
        elif form_type == "all":
            # Get multiple important form types
            # We'll need to make multiple requests
            pass
        
        try:
            logger.info(f"Fetching RSS feed for {form_type} filings...")
            
            all_filings = []
            
            # If "all", fetch each type separately for better results
            if form_type == "all":
                form_types_to_check = ["10-K", "10-Q", "8-K","S-1"]
                for specific_form in form_types_to_check:
                    params["type"] = specific_form
                    param_str = "&".join(f"{k}={v}" for k, v in params.items())
                    rss_url = f"{base_rss_url}?{param_str}"
                    
                    logger.info(f"Fetching {specific_form} filings from: {rss_url}")
                    
                    async with httpx.AsyncClient() as client:
                        response = await client.get(
                            rss_url,
                            headers={
                                "User-Agent": settings.SEC_USER_AGENT,
                                "Accept": "application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"
                            },
                            timeout=30.0
                        )
                        
                        if response.status_code == 200:
                            feed = feedparser.parse(response.text)
                            if hasattr(feed, 'entries'):
                                all_filings.extend(feed.entries)
                                logger.info(f"Found {len(feed.entries)} {specific_form} entries")
            else:
                # Single form type
                param_str = "&".join(f"{k}={v}" for k, v in params.items())
                rss_url = f"{base_rss_url}?{param_str}"
                
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        rss_url,
                        headers={
                            "User-Agent": settings.SEC_USER_AGENT,
                            "Accept": "application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"
                        },
                        timeout=30.0
                    )
                    response.raise_for_status()
                    
                    feed = feedparser.parse(response.text)
                    if hasattr(feed, 'entries'):
                        all_filings = feed.entries
            
            logger.info(f"Total entries to process: {len(all_filings)}")
            
            # Debug: Show first few entries
            if all_filings:
                logger.info("Sample entries after filtering:")
                for i, entry in enumerate(all_filings[:3]):
                    logger.info(f"Entry {i+1}: {entry.get('title', 'No title')}")
            
            filings = []
            cutoff_time = datetime.now() - timedelta(minutes=lookback_minutes)
            
            for entry in all_filings:
                try:
                    # Parse entry title
                    title = entry.get('title', '')
                    if not title:
                        continue
                    
                    # Enhanced regex patterns to handle various formats including (Filer) suffix
                    patterns = [
                        # Pattern 1: Form - Company (CIK) (Filer/Subject/etc)
                        r'^([\w\-/]+)\s*-\s*(.+?)\s*\((\d{1,10})\)(?:\s*\([^)]+\))*$',
                        # Pattern 2: Form - Company (CIK)
                        r'^([\w\-/]+)\s*-\s*(.+?)\s*\((\d{1,10})\)$',
                        # Pattern 3: Form - Company without CIK
                        r'^([\w\-/]+)\s*-\s*(.+?)$'
                    ]
                    
                    title_match = None
                    for pattern in patterns:
                        title_match = re.match(pattern, title)
                        if title_match:
                            break
                    
                    if not title_match:
                        # Log more details for debugging
                        logger.warning(f"Could not parse title format: '{title}'")
                        continue
                    
                    form = title_match.group(1).strip()
                    company_name = title_match.group(2).strip()
                    
                    # Clean up company name - remove any trailing suffixes
                    company_name = re.sub(r'\s*\([^)]*\)\s*$', '', company_name).strip()
                    
                    # Get CIK from match or from link
                    cik = None
                    if title_match.lastindex >= 3:
                        cik = title_match.group(3).zfill(10)
                    else:
                        # Try to extract from link
                        link = entry.get('link', '')
                        cik_match = re.search(r'CIK=(\d+)', link)
                        if cik_match:
                            cik = cik_match.group(1).zfill(10)
                    
                    if not cik:
                        # Try one more place - the summary field
                        summary = entry.get('summary', '')
                        cik_match = re.search(r'CIK[:\s]+(\d+)', summary)
                        if cik_match:
                            cik = cik_match.group(1).zfill(10)
                        else:
                            logger.warning(f"Could not find CIK for: '{title}'")
                            continue
                    
                    # Handle form variants (10-K/A, 8-K/A, etc.)
                    base_form = form.split('/')[0]
                    
                    # Only process forms we care about
                    if base_form not in ["10-K", "10-Q", "8-K", "S-1"]:
                        # Also check for special 8-K variants
                        if not form.startswith("8-K"):
                            continue
                    
                    # Extract accession number from link
                    link = entry.get('link', '')
                    acc_match = re.search(
                        r'AccessionNumber=(\d{10}-\d{2}-\d{6})',
                        link
                    )
                    
                    if not acc_match:
                        # Try alternative pattern
                        acc_match = re.search(
                            r'(\d{10}-\d{2}-\d{6})',
                            link
                        )
                    
                    accession_number = acc_match.group(1) if acc_match else ""
                    
                    # Parse date - try multiple formats
                    published = entry.get('published', entry.get('updated', ''))
                    filed_datetime = None
                    
                    date_formats = [
                        '%a, %d %b %Y %H:%M:%S %Z',  # Mon, 23 Jun 2025 16:30:00 EDT
                        '%Y-%m-%dT%H:%M:%S%z',       # 2025-06-23T16:30:00-04:00
                        '%Y-%m-%dT%H:%M:%S',         # 2025-06-23T16:30:00
                        '%Y-%m-%d %H:%M:%S',         # 2025-06-23 16:30:00
                    ]
                    
                    for fmt in date_formats:
                        try:
                            # Handle timezone abbreviations
                            date_str = published.replace('EDT', '-0400').replace('EST', '-0500')
                            date_str = date_str.replace('PDT', '-0700').replace('PST', '-0800')
                            filed_datetime = datetime.strptime(date_str, fmt)
                            break
                        except:
                            continue
                    
                    if not filed_datetime:
                        # Use current time as fallback
                        filed_datetime = datetime.now()
                        logger.debug(f"Could not parse date: {published}, using current time")
                    
                    # Remove timezone info for comparison
                    if filed_datetime.tzinfo:
                        filed_datetime = filed_datetime.replace(tzinfo=None)
                    
                    # Skip if older than lookback period
                    if filed_datetime < cutoff_time:
                        logger.debug(f"Skipping old filing from {filed_datetime}")
                        continue
                    
                    # Successfully parsed filing
                    filing_data = {
                        "cik": cik,
                        "form": form,
                        "company_name": company_name,
                        "filing_date": filed_datetime.strftime('%Y-%m-%d'),
                        "filing_datetime": filed_datetime,
                        "accession_number": accession_number,
                        "primary_document": "",  # Will get from detail API if needed
                        "rss_link": link,
                        "summary": entry.get('summary', '')[:200]  # First 200 chars
                    }
                    
                    filings.append(filing_data)
                    
                    # Log successful parsing for debugging
                    logger.debug(f"Successfully parsed: {form} - {company_name} (CIK: {cik})")
                    
                except Exception as e:
                    logger.error(f"Error parsing RSS entry: {e}", exc_info=True)
                    logger.debug(f"Failed entry title: '{entry.get('title', 'No title')}'")
                    continue
            
            # Sort by filing datetime (newest first)
            filings.sort(key=lambda x: x['filing_datetime'], reverse=True)
            
            logger.info(f"Successfully parsed {len(filings)} filings from RSS feed")
            
            # Log some statistics
            if filings:
                form_counts = {}
                for f in filings:
                    form_type = f['form'].split('/')[0]  # Base form type
                    form_counts[form_type] = form_counts.get(form_type, 0) + 1
                logger.info(f"Filing breakdown: {form_counts}")
            
            return filings
            
        except httpx.HTTPError as e:
            logger.error(f"Error fetching RSS feed: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in RSS parsing: {e}", exc_info=True)
            return []
    
    async def get_recent_submissions(self, lookback_minutes: int = 5) -> List[Dict]:
        """
        DEPRECATED - Use get_rss_filings instead
        Kept for backward compatibility
        """
        logger.warning("get_recent_submissions is deprecated. Use get_rss_filings instead.")
        return await self.get_rss_filings("all", lookback_minutes)
    
    async def get_company_info(self, cik: str) -> Optional[Dict]:
        """
        Get company information by CIK
        
        Args:
            cik: Central Index Key (padded to 10 digits)
            
        Returns:
            Company information or None
        """
        await self._rate_limit()
        
        # Pad CIK to 10 digits
        cik_padded = str(cik).zfill(10)
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/submissions/CIK{cik_padded}.json",
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                
                data = response.json()
                return {
                    "cik": data.get("cik"),
                    "name": data.get("name"),
                    "ticker": data.get("tickers", [None])[0] if data.get("tickers") else None,
                    "sic": data.get("sic"),
                    "sic_description": data.get("sicDescription"),
                    "category": data.get("category"),
                    "entity_type": data.get("entityType"),
                    "website": data.get("website")
                }
                
            except httpx.HTTPError as e:
                logger.error(f"Error fetching company info for CIK {cik}: {e}")
                return None
    
    async def get_filing_details(self, accession_number: str, cik: str) -> Optional[Dict]:
        """
        Get detailed filing information
        
        Args:
            accession_number: SEC accession number
            cik: Company CIK
            
        Returns:
            Detailed filing information
        """
        await self._rate_limit()
        
        # Format accession number for URL (remove dashes)
        acc_no_clean = accession_number.replace("-", "")
        
        async with httpx.AsyncClient() as client:
            try:
                # Get filing metadata
                url = f"{self.base_url}/Archives/edgar/data/{cik}/{acc_no_clean}/index.json"
                response = await client.get(url, headers=self.headers, timeout=30.0)
                response.raise_for_status()
                
                data = response.json()
                
                # Find primary document
                primary_doc = None
                for doc in data.get("directory", {}).get("item", []):
                    if doc.get("type") == "10-K" or doc.get("type") == "10-Q" or doc.get("type") == "8-K":
                        primary_doc = doc.get("name")
                        break
                
                return {
                    "accession_number": accession_number,
                    "cik": cik,
                    "primary_document": primary_doc,
                    "filing_date": data.get("filingDate"),
                    "documents": data.get("directory", {}).get("item", [])
                }
                
            except httpx.HTTPError as e:
                logger.error(f"Error fetching filing details: {e}")
                return None
    
    async def search_companies(self, query: str) -> List[Dict]:
        """
        Search for companies by name or ticker
        
        Args:
            query: Search query (company name or ticker)
            
        Returns:
            List of matching companies
        """
        await self._rate_limit()
        
        async with httpx.AsyncClient() as client:
            try:
                # Get company tickers mapping
                response = await client.get(
                    "https://www.sec.gov/files/company_tickers.json",
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                
                data = response.json()
                results = []
                
                # Search through the tickers
                query_upper = query.upper()
                for item in data.values():
                    ticker = item.get("ticker", "")
                    title = item.get("title", "")
                    
                    if query_upper in ticker or query_upper in title.upper():
                        results.append({
                            "cik": str(item.get("cik_str", "")).zfill(10),
                            "name": title,
                            "ticker": ticker
                        })
                        
                        if len(results) >= 10:
                            break
                
                return results
                
            except httpx.HTTPError as e:
                logger.error(f"Error searching companies: {e}")
                return []


# Create singleton instance
sec_client = SECClient()
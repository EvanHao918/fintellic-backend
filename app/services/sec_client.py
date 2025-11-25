import httpx
import asyncio
import feedparser
import re
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

# Reduce httpx log noise (513 requests per scan would flood logs)
logging.getLogger("httpx").setLevel(logging.WARNING)


class SECClient:
    """
    Client for interacting with SEC EDGAR API
    
    Data Source Strategy:
    - JSON submissions API: Primary method for 8-K/10-Q/10-K (100% reliable)
    - RSS feed: Only for S-1 (IPO filings from unknown CIKs)
    
    Rate Limit: 10 requests/second (SEC enforced)
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
        
        # ETag cache for JSON submissions (reduces bandwidth)
        self.etag_cache: Dict[str, str] = {}  # {cik: etag}
        
        # Supported form types for JSON scanning
        self.json_supported_forms = {"10-K", "10-Q", "8-K"}
        
    async def _rate_limit(self):
        """Ensure we don't exceed SEC rate limits"""
        now = datetime.now()
        time_since_last = (now - self.last_request_time).total_seconds()
        
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)
        
        self.last_request_time = datetime.now()
    
    async def get_rss_filings(self, form_type: str = "S-1", lookback_minutes: int = 60) -> List[Dict]:
        """
        Get filings from SEC RSS feed - NOW ONLY USED FOR S-1 (IPO) DISCOVERY
        
        Note: 8-K/10-Q/10-K now use JSON submissions API for reliability.
        RSS is kept only for S-1 because IPO companies have unknown CIKs.
        
        Args:
            form_type: "S-1" (primary use case) or "all" for backward compatibility
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
        elif form_type == "S-1":
            params["type"] = "S-1"
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
            # CRITICAL FIX: Use timezone-aware datetime for cutoff
            # Railway server may be in different timezone than development machine
            current_time_utc = datetime.now(timezone.utc)
            cutoff_time = current_time_utc - timedelta(minutes=lookback_minutes)
            
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
                    
                    logger.debug(f"📅 Parsing date for: {company_name} ({cik})")
                    logger.debug(f"   Published string: {published}")
                    
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
                            logger.debug(f"   ✅ Parsed with format: {fmt}")
                            logger.debug(f"   Parsed datetime: {filed_datetime}")
                            break
                        except:
                            continue
                    
                    if not filed_datetime:
                        # Use current time as fallback
                        filed_datetime = datetime.now()
                        logger.warning(f"⚠️  Could not parse date for {company_name}: {published}, using current time")
                    
                    # CRITICAL FIX: Convert to UTC for timezone-aware comparison
                    # Don't remove timezone info - convert to UTC instead
                    if filed_datetime.tzinfo:
                        # Convert to UTC
                        filed_datetime_utc = filed_datetime.astimezone(timezone.utc)
                    else:
                        # Naive datetime - assume it's already in UTC
                        filed_datetime_utc = filed_datetime.replace(tzinfo=timezone.utc)
                    
                    # Skip if older than lookback period (both are now UTC timezone-aware)
                    if filed_datetime_utc < cutoff_time:
                        # Only log at debug level to reduce noise
                        logger.debug(f"Filtered out (too old): {form} - {company_name} (CIK: {cik}), filed {filed_datetime_utc}")
                        continue
                    
                    # Successfully parsed filing
                    # Store as naive datetime for filing_datetime field (backward compatibility)
                    filing_datetime_naive = filed_datetime_utc.replace(tzinfo=None)
                    
                    filing_data = {
                        "cik": cik,
                        "form": form,
                        "company_name": company_name,
                        "filing_date": filing_datetime_naive.strftime('%Y-%m-%d'),
                        "filing_datetime": filing_datetime_naive,
                        "accession_number": accession_number,
                        "primary_document": "",  # Will get from detail API if needed
                        "rss_link": link,
                        "summary": entry.get('summary', '')[:200]  # First 200 chars
                    }
                    
                    filings.append(filing_data)
                    
                    # Log successful parsing at debug level
                    logger.debug(f"Parsed: {form} - {company_name} (CIK: {cik})")
                    
                except Exception as e:
                    logger.error(f"Error parsing RSS entry: {e}", exc_info=True)
                    logger.debug(f"Failed entry title: '{entry.get('title', 'No title')}'")
                    continue
            
            # Sort by filing datetime (newest first)
            filings.sort(key=lambda x: x['filing_datetime'], reverse=True)
            
            logger.info(f"Successfully parsed {len(filings)} filings from RSS feed (out of {len(all_filings)} total entries)")
            
            # Log breakdown only at debug level
            if filings:
                form_counts = {}
                for f in filings:
                    form_type = f['form'].split('/')[0]  # Base form type
                    form_counts[form_type] = form_counts.get(form_type, 0) + 1
                logger.debug(f"Filing breakdown: {form_counts}")
            
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


    # ==================== JSON Submissions API Methods ====================
    
    async def get_company_submissions(self, cik: str) -> Optional[Dict]:
        """
        Get recent filings for a single company via JSON submissions API
        
        Args:
            cik: Central Index Key (will be padded to 10 digits)
            
        Returns:
            Dict with recent filings or None if failed
        """
        await self._rate_limit()
        
        cik_padded = str(cik).zfill(10)
        url = f"{self.base_url}/submissions/CIK{cik_padded}.json"
        
        # Prepare headers with ETag if cached
        headers = self.headers.copy()
        cached_etag = self.etag_cache.get(cik_padded)
        if cached_etag:
            headers["If-None-Match"] = cached_etag
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers, timeout=30.0)
                
                # 304 Not Modified - no changes
                if response.status_code == 304:
                    return {"status": "not_modified", "cik": cik_padded, "filings": []}
                
                response.raise_for_status()
                
                # Update ETag cache
                new_etag = response.headers.get("ETag")
                if new_etag:
                    self.etag_cache[cik_padded] = new_etag
                
                data = response.json()
                
                # Extract recent filings
                recent = data.get("filings", {}).get("recent", {})
                if not recent:
                    return {"status": "ok", "cik": cik_padded, "filings": []}
                
                # Build filing list from parallel arrays
                filings = []
                forms = recent.get("form", [])
                accession_numbers = recent.get("accessionNumber", [])
                filing_dates = recent.get("filingDate", [])
                primary_documents = recent.get("primaryDocument", [])
                
                # Only process most recent filings (3 entries for real-time detection)
                for i in range(min(3, len(forms))):
                    form = forms[i] if i < len(forms) else ""
                    
                    # Only include supported form types (exact match, no /A variants)
                    if form not in self.json_supported_forms:
                        continue
                    
                    filings.append({
                        "form": form,
                        "accession_number": accession_numbers[i] if i < len(accession_numbers) else "",
                        "filing_date": filing_dates[i] if i < len(filing_dates) else "",
                        "primary_document": primary_documents[i] if i < len(primary_documents) else "",
                        "cik": cik_padded,
                        "company_name": data.get("name", ""),
                    })
                
                return {"status": "ok", "cik": cik_padded, "filings": filings}
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    logger.debug(f"CIK {cik_padded} not found")
                else:
                    logger.warning(f"HTTP error for CIK {cik_padded}: {e.response.status_code}")
                return None
            except Exception as e:
                logger.warning(f"Error fetching submissions for CIK {cik_padded}: {e}")
                return None
    
    async def get_batch_submissions(self, ciks: List[str], known_accessions: set) -> Dict:
        """
        Batch query submissions for multiple CIKs
        
        Args:
            ciks: List of CIKs to query
            known_accessions: Set of accession numbers already in database
            
        Returns:
            Dict with new filings and scan statistics
        """
        scan_start = datetime.now(timezone.utc)
        
        new_filings = []
        success_count = 0
        cached_count = 0
        error_count = 0
        
        for cik in ciks:
            result = await self.get_company_submissions(cik)
            
            if result is None:
                error_count += 1
                continue
            
            if result.get("status") == "not_modified":
                cached_count += 1
                success_count += 1
                continue
            
            success_count += 1
            
            # Check for new filings
            for filing in result.get("filings", []):
                accession = filing.get("accession_number", "")
                if accession and accession not in known_accessions:
                    new_filings.append(filing)
        
        scan_duration = (datetime.now(timezone.utc) - scan_start).total_seconds()
        
        # Log scan summary (single line)
        logger.info(
            f"JSON scan: {len(ciks)} CIKs in {scan_duration:.1f}s | "
            f"success={success_count} cached={cached_count} errors={error_count} | "
            f"new_filings={len(new_filings)}"
        )
        
        return {
            "new_filings": new_filings,
            "scan_duration": scan_duration,
            "success_count": success_count,
            "cached_count": cached_count,
            "error_count": error_count,
        }


# Create singleton instance
sec_client = SECClient()
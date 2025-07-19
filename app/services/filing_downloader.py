import httpx
import asyncio
import re
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
import logging
from typing import Optional, Dict, List
from urllib.parse import urlparse, parse_qs, unquote
from sqlalchemy.orm import Session

from app.models.filing import Filing, ProcessingStatus

logger = logging.getLogger(__name__)


class FilingDownloader:
    """
    Enhanced filing downloader with improvements from the fixing process
    
    Key improvements:
    - Better handling of iXBRL viewer links
    - Exclusion of exhibit files (EX-*)
    - Content validation after download
    - Priority-based document selection
    """
    
    def __init__(self):
        self.base_url = "https://www.sec.gov/Archives/edgar/data"
        self.headers = {
            'User-Agent': 'Fintellic/1.0 (contact@fintellic.com)',
            'Accept': 'text/html,application/xhtml+xml'
        }
        self.rate_limit_delay = 0.1  # SEC rate limit
        self.last_request_time = datetime.now()
        self.data_dir = Path("data/filings")
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    async def _rate_limit(self):
        """Respect SEC rate limits"""
        now = datetime.now()
        time_since_last = (now - self.last_request_time).total_seconds()
        
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)
        
        self.last_request_time = datetime.now()
    
    def _get_filing_directory(self, filing: Filing) -> Path:
        """
        Get the local directory path for storing filing files
        Maintains existing directory structure: data/filings/{cik}/{accession}/
        """
        # Remove dashes from accession number for directory name
        acc_no_clean = filing.accession_number.replace("-", "")
        return self.data_dir / filing.company.cik / acc_no_clean
    
    def _build_index_url(self, filing: Filing) -> str:
        """Build URL for the index.htm page"""
        # Handle different accession number formats
        # Format: 0000950170-25-095711 -> need to keep it as is for URL
        acc_no = filing.accession_number
        
        # For the directory, we need the full accession number with dashes
        # But some systems remove dashes, so we need to be flexible
        
        # CIK needs to be padded to 10 digits for the URL
        cik_padded = filing.company.cik.zfill(10)
        
        # Try the standard format first
        return f"{self.base_url}/{cik_padded}/{acc_no}/-index.htm"
    
    def _is_ixbrl_viewer_page(self, html_content: str) -> bool:
        """Check if the page is an iXBRL viewer page"""
        # Check first 2000 characters for efficiency
        sample = html_content[:2000] if len(html_content) > 2000 else html_content
        return 'loadViewer' in sample and ('ixvFrame' in sample or 'ixbrl' in sample.lower())
    
    def _extract_url_from_ixbrl_link(self, href: str) -> str:
        """
        Extract the actual document URL from iXBRL viewer link
        Example: /ix?doc=/Archives/edgar/data/37996/000003799625000141/f-20250716.htm
        Returns: /Archives/edgar/data/37996/000003799625000141/f-20250716.htm
        """
        if '/ix?doc=' in href:
            # Extract the doc parameter
            doc_start = href.find('doc=') + 4
            doc_end = href.find('&', doc_start) if '&' in href[doc_start:] else len(href)
            doc_path = href[doc_start:doc_end]
            return unquote(doc_path)
        return href
    
    def _parse_index_page_enhanced(self, html_content: str, filing_type: str) -> Optional[Dict]:
        """
        Enhanced index parser with improvements from the fixing process
        
        Improvements:
        1. Better main document identification (excludes EX-* files)
        2. Priority handling for iXBRL links
        3. Support for more table layouts
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Check if this is an iXBRL viewer page itself
        if self._is_ixbrl_viewer_page(html_content):
            logger.info("Detected iXBRL viewer page, skipping standard parsing")
            return None
        
        # Candidate documents list, sorted by priority
        candidates = []
        
        # Find all tables
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                
                if len(cells) < 3:
                    continue
                
                # Extract row information
                row_text = ' '.join([cell.get_text(strip=True) for cell in cells])
                
                # Skip header rows
                if 'Description' in row_text and 'Type' in row_text:
                    continue
                
                # Find type information
                type_found = None
                doc_link = None
                description = ""
                
                # Check each cell
                for i, cell in enumerate(cells):
                    cell_text = cell.get_text(strip=True)
                    
                    # Check if it contains document type
                    if filing_type in cell_text:
                        type_found = cell_text
                    
                    # Find link
                    link = cell.find('a')
                    if link and link.get('href'):
                        doc_link = link
                    
                    # Collect description
                    if cell_text and len(cell_text) > 10 and 'EX-' not in cell_text:
                        description = cell_text
                
                # If found matching document type and link
                if type_found and doc_link:
                    href = doc_link['href']
                    filename = doc_link.get_text(strip=True) or href.split('/')[-1]
                    
                    # Calculate priority
                    priority = 0
                    
                    # Check if it's an exhibit file
                    if re.search(r'EX-\d+', type_found) or re.search(r'ex-?\d+', filename, re.I):
                        priority = -10  # Lowest priority
                        continue  # Skip exhibit files directly
                    
                    # Check if it's an iXBRL link
                    if '/ix?doc=' in href:
                        priority = 10  # High priority
                        actual_url = self._extract_url_from_ixbrl_link(href)
                        filename = actual_url.split('/')[-1]
                        href = actual_url
                    
                    # Check for exact document type match
                    if type_found == filing_type:
                        priority += 5
                    
                    candidates.append({
                        'filename': filename,
                        'url': href,
                        'type': type_found,
                        'description': description,
                        'priority': priority
                    })
        
        # Sort by priority and return the best candidate
        if candidates:
            candidates.sort(key=lambda x: x['priority'], reverse=True)
            best = candidates[0]
            del best['priority']  # Remove internal priority field
            
            logger.info(f"Selected document: {best['filename']} (type: {best['type']})")
            return best
        
        # If nothing found, use fallback logic
        return self._parse_index_page_fallback(soup, filing_type)
    
    def _parse_index_page_fallback(self, soup: BeautifulSoup, filing_type: str) -> Optional[Dict]:
        """
        Fallback parsing method for non-standard formats
        """
        # Find all links
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link['href']
            text = link.text.strip()
            
            # Skip obvious exhibit files
            if re.search(r'ex-?\d+', href, re.I) or re.search(r'ex-?\d+', text, re.I):
                continue
            
            # Check iXBRL links
            if '/ix?doc=' in href:
                # Extract actual path
                actual_url = self._extract_url_from_ixbrl_link(href)
                
                # Check if it contains document type
                if filing_type.lower() in actual_url.lower():
                    filename = actual_url.split('/')[-1]
                    logger.info(f"Found iXBRL link in fallback: {href} -> {actual_url}")
                    
                    return {
                        'filename': filename,
                        'url': actual_url,
                        'type': filing_type,
                        'description': 'Main Document'
                    }
            
            # Check regular links
            if filing_type.lower() in href.lower() or filing_type.lower().replace('-', '') in href.lower():
                return {
                    'filename': text or href.split('/')[-1],
                    'url': href,
                    'type': filing_type,
                    'description': 'Main Document'
                }
        
        return None
    
    def _parse_index_page(self, html_content: str, filing_type: str) -> Optional[Dict]:
        """
        Parse SEC index.htm to find the main document
        Now uses enhanced parsing as primary method
        """
        # Try enhanced parsing first
        result = self._parse_index_page_enhanced(html_content, filing_type)
        if result:
            return result
        
        # Fall back to original parsing if enhanced fails
        logger.warning("Enhanced parsing failed, trying original method")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find the document table
        tables = soup.find_all('table', {'summary': 'Document Format Files'})
        if not tables:
            # Try alternative table structure
            tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    # Ford case layout: Seq | Description | Document | Type | Size
                    # Standard layout: Type | Description | Document
                    
                    if len(cells) >= 4:
                        # New layout (Ford case)
                        desc_text = cells[1].text.strip()
                        doc_cell = cells[2]
                        type_text = cells[3].text.strip()
                    else:
                        # Old layout
                        type_text = cells[0].text.strip()
                        desc_text = cells[1].text.strip()
                        doc_cell = cells[2]
                    
                    # Skip exhibit files
                    if 'EX-' in type_text:
                        continue
                    
                    # Look for matching filing type
                    if (filing_type.lower() in type_text.lower() or 
                        filing_type.lower().replace('-', '') in type_text.lower() or
                        filing_type.lower() in desc_text.lower()):
                        
                        # Extract document link
                        link = doc_cell.find('a')
                        if link and link.get('href'):
                            href = link['href']
                            
                            # Handle iXBRL viewer links
                            if '/ix?doc=' in href:
                                logger.info(f"Found iXBRL viewer link: {href}")
                                actual_url = self._extract_url_from_ixbrl_link(href)
                                logger.info(f"Extracted actual document URL: {actual_url}")
                                filename = actual_url.split('/')[-1] if '/' in actual_url else actual_url
                                
                                return {
                                    'filename': filename,
                                    'url': actual_url,
                                    'type': type_text,
                                    'description': desc_text
                                }
                            else:
                                return {
                                    'filename': link.text.strip(),
                                    'url': href,
                                    'type': type_text,
                                    'description': desc_text
                                }
        
        return None
    
    def _validate_downloaded_content(self, content: bytes, filing_type: str) -> bool:
        """
        Validate that downloaded content is a valid main document
        
        Returns:
            True if content appears to be a valid main document
        """
        if len(content) < 5000:  # Less than 5KB is suspicious
            logger.warning(f"Document suspiciously small: {len(content)} bytes")
            return False
        
        # Decode first 1000 characters for checking
        try:
            sample = content[:1000].decode('utf-8', errors='ignore')
        except:
            return True  # If can't decode, assume it's a binary file
        
        # Check if it's an exhibit file
        if '<TYPE>EX-' in sample:
            logger.warning("Downloaded content appears to be an exhibit file")
            return False
        
        # Check if it's an iXBRL viewer
        if 'loadViewer' in sample and 'ixvFrame' in sample:
            logger.warning("Downloaded content is still an iXBRL viewer")
            return False
        
        # Check for expected document type markers
        expected_markers = [
            f'<TYPE>{filing_type}',
            f'FORM {filing_type}',
            'UNITED STATES SECURITIES AND EXCHANGE COMMISSION'
        ]
        
        if any(marker in sample.upper() for marker in expected_markers):
            return True
        
        # For documents without TYPE tags, check for financial content
        financial_indicators = [
            'financial statements',
            'consolidated',
            'balance sheet',
            'income statement',
            'cash flow',
            'management discussion'
        ]
        
        content_lower = content[:5000].decode('utf-8', errors='ignore').lower()
        if any(indicator in content_lower for indicator in financial_indicators):
            return True
        
        logger.warning("Downloaded content validation failed")
        return False
    
    async def download_filing(self, db: Session, filing: Filing) -> bool:
        """
        Download the main filing document
        
        Enhanced with better document selection and validation
        """
        try:
            # Update status to downloading (expected by the system)
            filing.status = ProcessingStatus.DOWNLOADING
            filing.processing_started_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Starting download for {filing.company.ticker} {filing.filing_type.value} "
                       f"({filing.accession_number})")
            
            # Create directory for this filing (maintaining existing structure)
            filing_dir = self._get_filing_directory(filing)
            filing_dir.mkdir(parents=True, exist_ok=True)
            
            async with httpx.AsyncClient(headers=self.headers, timeout=30.0) as client:
                # Try multiple URL formats since SEC has inconsistent patterns
                urls_to_try = []
                
                # Format 1: Most common - CIK without leading zeros
                cik_no_zeros = filing.company.cik.lstrip('0')
                urls_to_try.append(f"{self.base_url}/{cik_no_zeros}/{filing.accession_number}/-index.htm")
                
                # Format 2: With padded CIK (less common)
                cik_padded = filing.company.cik.zfill(10)
                urls_to_try.append(f"{self.base_url}/{cik_padded}/{filing.accession_number}/-index.htm")
                
                # Format 3: Without dashes in accession number
                acc_no_clean = filing.accession_number.replace("-", "")
                urls_to_try.append(f"{self.base_url}/{cik_no_zeros}/{acc_no_clean}/-index.htm")
                
                # Format 4: Alternative index names
                urls_to_try.append(f"{self.base_url}/{cik_no_zeros}/{filing.accession_number}/index.htm")
                
                index_content = None
                successful_url = None
                
                for url in urls_to_try:
                    try:
                        logger.debug(f"Trying URL: {url}")
                        await self._rate_limit()
                        response = await client.get(url)
                        
                        if response.status_code == 200:
                            index_content = response.content
                            successful_url = url
                            logger.info(f"Successfully fetched index from: {url}")
                            break
                    except Exception as e:
                        logger.debug(f"Failed to fetch from {url}: {e}")
                        continue
                
                if not index_content:
                    raise Exception(f"Failed to fetch index page - tried {len(urls_to_try)} URL formats")
                
                # Save index.htm for reference (expected by system)
                index_path = filing_dir / "index.htm"
                with open(index_path, 'wb') as f:
                    f.write(index_content)
                
                # Check if this is an iXBRL viewer page that needs special handling
                index_text = index_content.decode('utf-8', errors='ignore')
                
                if self._is_ixbrl_viewer_page(index_text):
                    logger.warning("Index page is an iXBRL viewer, trying direct document patterns")
                    # Try common document patterns directly
                    main_doc = await self._try_common_patterns(client, filing)
                else:
                    # Step 2: Parse index to find main document (using enhanced parser)
                    main_doc = self._parse_index_page(index_text, filing.filing_type.value)
                    
                    if not main_doc:
                        # Fallback: try to guess the document name
                        logger.warning("Could not find main document in index, trying fallback methods")
                        main_doc = await self._try_common_patterns(client, filing)
                
                if main_doc:
                    # Step 3: Download the main document
                    doc_url = main_doc['url']
                    
                    # Handle relative URLs
                    if not doc_url.startswith('http'):
                        # Use the base URL from the successful index fetch
                        base_url_parts = successful_url.rsplit('/', 1)[0]
                        
                        if doc_url.startswith('/'):
                            doc_url = f"https://www.sec.gov{doc_url}"
                        else:
                            doc_url = f"{base_url_parts}/{doc_url}"
                    
                    logger.info(f"Downloading main document from: {doc_url}")
                    
                    await self._rate_limit()
                    doc_response = await client.get(doc_url, timeout=60.0)
                    
                    if doc_response.status_code == 200:
                        doc_content = doc_response.content
                        
                        # Validate content
                        if not self._validate_downloaded_content(doc_content, filing.filing_type.value):
                            logger.warning("Downloaded content failed validation")
                            # Try alternative methods
                            main_doc = await self._try_common_patterns(client, filing)
                            if main_doc:
                                doc_url = f"{base_url_parts}/{main_doc['url']}"
                                doc_response = await client.get(doc_url, timeout=60.0)
                                if doc_response.status_code == 200:
                                    doc_content = doc_response.content
                                else:
                                    raise Exception("All download attempts failed validation")
                        
                        # Determine filename
                        filename = main_doc['filename']
                        if not filename.endswith(('.htm', '.html', '.txt')):
                            filename = f"{filing.filing_type.value.lower()}.htm"
                        
                        # Save the document
                        doc_path = filing_dir / filename
                        with open(doc_path, 'wb') as f:
                            f.write(doc_content)
                        
                        logger.info(f"✅ Successfully downloaded {filename} "
                                   f"({len(doc_content):,} bytes)")
                        
                        # Update filing record (expected by system)
                        filing.status = ProcessingStatus.PARSING
                        filing.primary_doc_url = doc_url
                        db.commit()
                        
                        return True
                    else:
                        raise Exception(f"Failed to download document: HTTP {doc_response.status_code}")
                else:
                    # Even if we can't find the main document, we have the index
                    # Mark as successful to allow text extraction to try
                    logger.warning("Could not find main document, but saved index.htm")
                    filing.status = ProcessingStatus.PARSING
                    filing.primary_doc_url = successful_url
                    db.commit()
                    return True
                    
        except Exception as e:
            logger.error(f"Error downloading filing {filing.accession_number}: {e}")
            
            # Update status to failed (expected by system)
            filing.status = ProcessingStatus.FAILED
            filing.error_message = str(e)
            db.commit()
            
            return False
    
    async def _try_common_patterns(self, client: httpx.AsyncClient, filing: Filing) -> Optional[Dict]:
        """
        Try common filename patterns when index parsing fails
        Enhanced to handle more patterns
        """
        # Generate various possible patterns
        date_str = filing.filing_date.strftime('%Y%m%d')
        ticker = filing.company.ticker.lower()
        form_type = filing.filing_type.value.lower().replace('-', '')
        
        common_patterns = [
            # Standard patterns
            f"{filing.filing_type.value.lower()}.htm",
            f"{filing.filing_type.value.lower()}.html",
            f"form{form_type}.htm",
            
            # Company-specific patterns
            f"{ticker}-{date_str}.htm",
            f"{ticker}_{date_str}.htm",
            f"{ticker}{date_str}.htm",
            
            # Form-specific patterns
            f"{form_type}.htm",
            f"{form_type}_{date_str}.htm",
            f"{form_type}-{date_str}.htm",
            
            # Generic patterns
            "primary_doc.htm",
            "filing.htm",
            
            # Special patterns for specific companies (like Ford's f-20250716.htm)
            f"f-{date_str}.htm",
            f"{ticker[0]}-{date_str}.htm" if ticker else None,
            
            # Patterns with underscores
            f"{ticker}_{form_type}.htm",
            f"{form_type}_{ticker}.htm",
        ]
        
        # Remove None values
        common_patterns = [p for p in common_patterns if p]
        
        acc_no_clean = filing.accession_number.replace("-", "")
        cik_clean = filing.company.cik.lstrip('0')
        base_url = f"{self.base_url}/{cik_clean}/{filing.accession_number}"
        
        for pattern in common_patterns:
            try:
                test_url = f"{base_url}/{pattern}"
                logger.debug(f"Trying pattern: {test_url}")
                
                await self._rate_limit()
                response = await client.head(test_url, timeout=5.0)
                
                if response.status_code == 200:
                    logger.info(f"Found document using pattern: {pattern}")
                    return {
                        'filename': pattern,
                        'url': pattern,
                        'type': filing.filing_type.value,
                        'description': 'Main Document (guessed)'
                    }
            except:
                continue
        
        return None
    
    def get_filing_path(self, filing: Filing) -> Optional[Path]:
        """
        Get the path to the downloaded filing document
        Used by text_extractor.py to find the file
        """
        filing_dir = self._get_filing_directory(filing)
        
        if not filing_dir.exists():
            return None
        
        # Look for the main document
        # Priority order: .htm, .html, .txt
        for pattern in ['*.htm', '*.html', '*.txt']:
            files = list(filing_dir.glob(pattern))
            # Exclude index.htm and exhibit files
            files = [f for f in files if f.name != 'index.htm' and not re.search(r'ex-?\d+', f.name, re.I)]
            if files:
                # Return the largest file (likely the main document)
                return max(files, key=lambda f: f.stat().st_size)
        
        # If no document found, return index.htm as fallback
        index_path = filing_dir / 'index.htm'
        if index_path.exists():
            return index_path
        
        return None


# Create singleton instance (expected by the system)
filing_downloader = FilingDownloader()
import httpx
import asyncio
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
import logging
from typing import Optional, Dict, List
from sqlalchemy.orm import Session

from app.models.filing import Filing, ProcessingStatus

logger = logging.getLogger(__name__)


class FilingDownloader:
    """
    Enhanced filing downloader that properly integrates with the system
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
    
    def _parse_index_page(self, html_content: str, filing_type: str) -> Optional[Dict]:
        """
        Parse SEC index.htm to find the main document
        Returns document info or None if not found
        """
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
                    # Check if this row contains our filing type
                    type_cell = cells[0].text.strip()
                    desc_cell = cells[1].text.strip()
                    doc_cell = cells[2]
                    
                    # Look for matching filing type
                    if filing_type.lower() in type_cell.lower() or \
                       filing_type.lower().replace('-', '') in type_cell.lower():
                        # Extract document link
                        link = doc_cell.find('a')
                        if link and link.get('href'):
                            return {
                                'filename': link.text.strip(),
                                'url': link['href'],
                                'type': type_cell,
                                'description': desc_cell
                            }
        
        # Fallback: look for any document that might be the main filing
        all_links = soup.find_all('a', href=True)
        for link in all_links:
            href = link['href']
            text = link.text.strip().lower()
            
            # Common patterns for main documents
            if any(pattern in href.lower() for pattern in [
                filing_type.lower(),
                filing_type.lower().replace('-', ''),
                'form' + filing_type.lower().replace('-', ''),
                filing_type.lower() + '.htm'
            ]):
                return {
                    'filename': link.text.strip(),
                    'url': href,
                    'type': filing_type,
                    'description': 'Main Document'
                }
        
        return None
    
    async def download_filing(self, db: Session, filing: Filing) -> bool:
        """
        Download the main filing document
        
        This method maintains the existing interface and behavior expected by filing_tasks.py:
        - Updates filing status throughout the process
        - Creates directory structure as expected
        - Returns True/False for success/failure
        - Handles all error cases gracefully
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
                
                # Step 2: Parse index to find main document
                main_doc = self._parse_index_page(index_content.decode('utf-8', errors='ignore'), filing.filing_type.value)
                
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
                        # Determine filename
                        filename = main_doc['filename']
                        if not filename.endswith(('.htm', '.html', '.txt')):
                            filename = f"{filing.filing_type.value.lower()}.htm"
                        
                        # Save the document
                        doc_path = filing_dir / filename
                        with open(doc_path, 'wb') as f:
                            f.write(doc_response.content)
                        
                        logger.info(f"✅ Successfully downloaded {filename} "
                                   f"({len(doc_response.content):,} bytes)")
                        
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
        """
        common_patterns = [
            f"{filing.filing_type.value.lower()}.htm",
            f"{filing.filing_type.value.lower()}.html",
            f"form{filing.filing_type.value.lower().replace('-', '')}.htm",
            f"{filing.company.ticker.lower()}-{filing.filing_date.strftime('%Y%m%d')}.htm",
            f"{filing.filing_type.value.lower().replace('-', '')}.htm",
            "primary_doc.htm"
        ]
        
        acc_no_clean = filing.accession_number.replace("-", "")
        cik_clean = filing.company.cik.lstrip('0')
        base_url = f"{self.base_url}/{cik_clean}/{acc_no_clean}"
        
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
            # Exclude index.htm
            files = [f for f in files if f.name != 'index.htm']
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
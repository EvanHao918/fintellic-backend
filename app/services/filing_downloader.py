# app/services/filing_downloader.py
"""
Filing Downloader Service
Downloads SEC filing documents (HTML and XBRL) from EDGAR
"""
import os
import httpx
import asyncio
from typing import Optional, Dict, List, TYPE_CHECKING
from datetime import datetime
from pathlib import Path
import logging

from sqlalchemy.orm import Session
from app.core.config import settings

# Avoid circular imports
if TYPE_CHECKING:
    from app.models.filing import Filing

logger = logging.getLogger(__name__)


class FilingDownloader:
    """
    Downloads SEC filing documents from EDGAR
    """
    
    def __init__(self):
        # SEC base URL for archived documents
        self.base_url = "https://www.sec.gov/Archives/edgar/data"
        
        # Headers required by SEC
        self.headers = {
            "User-Agent": settings.SEC_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        
        # Local storage directory
        self.data_dir = Path("data/filings")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Rate limiting (SEC allows 10 requests per second)
        self.rate_limit_delay = 0.1  # 100ms between requests
        self.last_request_time = datetime.min
    
    async def test_connection(self):
        """
        Test if we can connect to SEC EDGAR
        """
        test_url = "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.head(
                    test_url, 
                    headers=self.headers,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    logger.info("✅ Successfully connected to SEC EDGAR")
                    return True
                else:
                    logger.error(f"❌ SEC EDGAR returned status {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Failed to connect to SEC EDGAR: {e}")
            return False
    
    async def _rate_limit(self):
        """
        Ensure we don't exceed SEC rate limits
        """
        now = datetime.now()
        time_since_last = (now - self.last_request_time).total_seconds()
        
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)
        
        self.last_request_time = datetime.now()
    
    def _get_filing_directory(self, filing) -> Path:
        """
        Get the local directory path for storing filing files
        """
        # Create directory structure: data/filings/{cik}/{accession_number}/
        return self.data_dir / filing.company.cik / filing.accession_number.replace("-", "")
    
    def _build_filing_url(self, filing, filename: str) -> str:
        """
        Build the full URL for a filing document
        """
        # Remove dashes from accession number for URL
        acc_no_clean = filing.accession_number.replace("-", "")
        
        # Remove leading zeros from CIK
        cik_clean = filing.company.cik.lstrip('0')
        
        # Build URL: https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no_clean}/{filename}
        return f"{self.base_url}/{cik_clean}/{acc_no_clean}/{filename}"
    
    async def download_filing(self, db: Session, filing) -> bool:
        """
        Download the main filing document
        
        Args:
            db: Database session
            filing: Filing object to download
            
        Returns:
            True if successful, False otherwise
        """
        from app.models.filing import ProcessingStatus  # Import here to avoid circular import
        
        try:
            # Update status to downloading
            filing.status = ProcessingStatus.DOWNLOADING
            filing.processing_started_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Starting download for {filing.company.ticker} {filing.filing_type.value} "
                       f"({filing.accession_number})")
            
            # Create directory for this filing
            filing_dir = self._get_filing_directory(filing)
            filing_dir.mkdir(parents=True, exist_ok=True)
            
            # First, let's try to access the index page to find the correct filename
            # Remove dashes from accession number
            acc_no_clean = filing.accession_number.replace("-", "")
            # Remove leading zeros from CIK
            cik_clean = filing.company.cik.lstrip('0')
            
            # Build index URL
            index_url = f"{self.base_url}/{cik_clean}/{acc_no_clean}/{filing.accession_number}-index.htm"
            
            logger.info(f"Checking index page: {index_url}")
            
            # Try to get the index page
            await self._rate_limit()
            
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    index_url,
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info(f"✅ Found index page")
                    
                    # Parse the index page to find document links
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Find the document table
                    tables = soup.find_all('table', {'class': 'tableFile'})
                    if not tables:
                        # Try alternative table format
                        tables = soup.find_all('table')
                    
                    documents_found = []
                    
                    for table in tables:
                        rows = table.find_all('tr')
                        for row in rows:
                            cells = row.find_all('td')
                            if len(cells) >= 3:
                                # Usually: Sequence | Description | Document | Type | Size
                                link_cell = cells[2] if len(cells) > 2 else None
                                if link_cell:
                                    link = link_cell.find('a')
                                    if link and link.get('href'):
                                        doc_url = link.get('href')
                                        doc_text = link.text.strip()
                                        
                                        # Make URL absolute if needed
                                        if not doc_url.startswith('http'):
                                            if doc_url.startswith('/'):
                                                doc_url = f"https://www.sec.gov{doc_url}"
                                            else:
                                                # Relative to current directory
                                                doc_url = f"{self.base_url}/{cik_clean}/{acc_no_clean}/{doc_url}"
                                        
                                        # Check if this is the main document
                                        if filing.filing_type.value.lower() in doc_text.lower() or \
                                           filing.filing_type.value.lower().replace('-', '') in doc_text.lower():
                                            documents_found.append({
                                                'url': doc_url,
                                                'filename': doc_text,
                                                'is_primary': True
                                            })
                                            logger.info(f"Found primary document: {doc_text}")
                    
                    # Download the primary document if found
                    if documents_found:
                        primary_doc = documents_found[0]  # Take first matching document
                        
                        logger.info(f"Downloading primary document from: {primary_doc['url']}")
                        
                        # Download the actual filing document
                        await self._rate_limit()
                        doc_response = await client.get(
                            primary_doc['url'],
                            headers=self.headers,
                            timeout=60.0
                        )
                        
                        if doc_response.status_code == 200:
                            # Save with original filename or create one
                            filename = primary_doc['filename']
                            if not filename.endswith(('.htm', '.html', '.txt')):
                                filename = f"{filing.filing_type.value.lower()}.htm"
                            
                            doc_path = filing_dir / filename
                            with open(doc_path, 'wb') as f:
                                f.write(doc_response.content)
                            
                            logger.info(f"✅ Downloaded {filename} ({len(doc_response.content):,} bytes)")
                            
                            # Also save the index page for reference
                            index_path = filing_dir / "index.htm"
                            with open(index_path, 'wb') as f:
                                f.write(response.content)
                            
                            # Update filing record
                            filing.status = ProcessingStatus.PARSING
                            filing.primary_doc_url = primary_doc['url']
                            db.commit()
                            
                            return True
                        else:
                            logger.warning(f"Failed to download document: HTTP {doc_response.status_code}")
                    else:
                        logger.warning("No primary document found in index page")
                        # Still save the index page
                        index_path = filing_dir / "index.htm"
                        with open(index_path, 'wb') as f:
                            f.write(response.content)
                        
                        # Update as successful (we at least got the index)
                        filing.status = ProcessingStatus.PARSING
                        filing.primary_doc_url = index_url
                        db.commit()
                        return True
                else:
                    raise Exception(f"HTTP {response.status_code} when accessing index page {index_url}")
                    
        except Exception as e:
            logger.error(f"Error downloading filing {filing.accession_number}: {e}")
            
            # Update status to failed
            filing.status = ProcessingStatus.FAILED
            filing.error_message = str(e)
            db.commit()
            
            return False


# Create singleton instance
filing_downloader = FilingDownloader()
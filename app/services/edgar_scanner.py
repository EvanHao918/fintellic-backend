from typing import List, Dict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging
import json
from pathlib import Path

from app.services.sec_client import sec_client
from app.models.company import Company
from app.models.filing import Filing, FilingType, ProcessingStatus
from app.core.database import SessionLocal
from app.core.config import settings
from app.tasks.filing_tasks import process_filing_task  # Added for auto-triggering

logger = logging.getLogger(__name__)


class EDGARScanner:
    """
    Scans SEC EDGAR for new filings using RSS feeds
    More efficient than polling individual companies
    """
    
    def __init__(self):
        self.scan_interval_minutes = 1  # Check RSS every minute
        self.supported_forms = ["10-K", "10-Q", "8-K", "S-1"]
        
        # Load S&P 500 companies from JSON file
        self.sp500_companies = self._load_sp500_companies()
        self.sp500_ciks = {company['cik'] for company in self.sp500_companies}
        
        # Debug output
        if self.sp500_ciks:
            logger.info(f"✅ Loaded {len(self.sp500_ciks)} S&P 500 companies for monitoring")
            # Show first few companies as confirmation
            sample = list(self.sp500_ciks)[:5]
            logger.info(f"Sample CIKs: {sample}")
        else:
            logger.error("❌ No S&P 500 companies loaded! Check data/sp500_companies.json")
    
    def _load_sp500_companies(self) -> list:
        """Load S&P 500 companies from JSON file"""
        json_path = Path(__file__).parent.parent / "data" / "sp500_companies.json"
        
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
                companies = data.get('companies', [])
                logger.info(f"Successfully loaded {len(companies)} S&P 500 companies from {json_path}")
                return companies
        except FileNotFoundError:
            logger.error(f"S&P 500 companies file not found at {json_path}")
            logger.info("Please run: python scripts/fetch_sp500.py")
            return []
        except Exception as e:
            logger.error(f"Error loading S&P 500 companies: {e}")
            return []
        
    async def scan_for_new_filings(self) -> List[Dict]:
        """
        Main scanning method - uses RSS for efficiency
        
        Returns:
            List of new filings discovered
        """
        logger.info("Starting EDGAR RSS scan...")
        logger.info(f"DEBUG: Monitoring {len(self.sp500_ciks)} S&P 500 companies")
        
        # Get recent filings from RSS (last 2 minutes to ensure overlap)
        all_rss_filings = await sec_client.get_rss_filings(
            form_type="all",
            lookback_minutes=self.scan_interval_minutes + 1
        )
        
        if not all_rss_filings:
            logger.info("No new filings found in RSS feed")
            return []
        
        # Filter for S&P 500 companies (except S-1 filings)
        sp500_filings = []
        for f in all_rss_filings:
            # S-1 filings (IPOs) are not limited to S&P 500 companies
            if f['form'] == 'S-1':
                sp500_filings.append(f)
                logger.info(f"Including S-1 filing from {f.get('company_name', 'Unknown')} (CIK: {f['cik']})")
            elif f['cik'] in self.sp500_ciks:
                sp500_filings.append(f)
        
        logger.info(f"Found {len(sp500_filings)} relevant filings out of {len(all_rss_filings)} total")
        
        # Log some examples if we found filings
        if sp500_filings:
            for filing in sp500_filings[:3]:  # Show first 3
                if filing['form'] == 'S-1':
                    logger.info(f"IPO filing: {filing.get('company_name', 'Unknown')} - S-1 ({filing['filing_date']})")
                else:
                    company = next((c for c in self.sp500_companies if c['cik'] == filing['cik']), None)
                    if company:
                        logger.info(f"S&P 500 filing: {company['ticker']} - {filing['form']} ({filing['filing_date']})")
        
        # Process each filing
        new_filings = []
        db = SessionLocal()
        
        try:
            for rss_filing in sp500_filings:
                # Check if we already have this filing
                existing = db.query(Filing).filter(
                    Filing.accession_number == rss_filing["accession_number"]
                ).first()
                
                if existing:
                    logger.debug(f"Filing {rss_filing['accession_number']} already exists")
                    continue
                
                # Get or create company
                company = await self._get_or_create_company(
                    db, rss_filing["cik"], rss_filing.get("company_name", "")
                )
                
                if not company:
                    logger.warning(f"Could not find/create company for CIK {rss_filing['cik']}")
                    continue
                
                # Create new filing record
                filing = self._create_filing_record(company.id, rss_filing)
                db.add(filing)
                
                # Need to flush to get the filing ID before triggering task
                db.flush()
                
                new_filings.append({
                    "company": company.name,
                    "ticker": company.ticker,
                    "form_type": rss_filing["form"],
                    "filing_date": rss_filing["filing_date"],
                    "accession_number": rss_filing["accession_number"],
                    "discovery_method": "RSS"
                })
                
                logger.info(
                    f"New filing discovered: {company.ticker} - {rss_filing['form']} "
                    f"({rss_filing['filing_date']}) via RSS"
                )
                
                # Automatically trigger Celery task to process this filing
                try:
                    # Queue the filing for processing
                    task = process_filing_task.delay(filing.id)
                    
                    logger.info(
                        f"✅ Queued filing {filing.id} for processing. "
                        f"Celery task ID: {task.id}"
                    )
                    
                    # Optional: Store task ID in filing record for tracking
                    # filing.celery_task_id = task.id
                    
                except Exception as e:
                    logger.error(f"❌ Failed to queue filing for processing: {e}")
                    # Continue even if queueing fails - filing is still saved
            
            # Commit all new filings
            if new_filings:
                db.commit()
                logger.info(f"Added {len(new_filings)} new filings to database")
            
            return new_filings
            
        except Exception as e:
            logger.error(f"Error during scan: {e}")
            db.rollback()
            return []
        finally:
            db.close()
    
    async def _get_or_create_company(self, db: Session, cik: str, company_name: str = "") -> Company:
        """
        Get company from database or create if doesn't exist
        
        Args:
            db: Database session
            cik: Company CIK
            company_name: Company name from RSS
            
        Returns:
            Company object or None
        """
        # Check if company exists
        company = db.query(Company).filter(Company.cik == cik).first()
        if company:
            return company
        
        # Look up company in our S&P 500 list
        sp500_company = next((c for c in self.sp500_companies if c['cik'] == cik), None)
        
        if sp500_company:
            # Use S&P 500 data
            company_info = {
                "cik": cik,
                "name": sp500_company['name'],
                "ticker": sp500_company['ticker']
            }
            is_sp500 = True
        else:
            # Fetch from SEC API as fallback (for S-1 filings from non-S&P 500 companies)
            company_info = await sec_client.get_company_info(cik)
            if not company_info:
                logger.warning(f"Could not fetch info for CIK {cik}")
                company_info = {
                    "cik": cik,
                    "name": company_name,
                    "ticker": f"CIK{cik}"
                }
            is_sp500 = False
        
        # Create new company record
        company = Company(
            cik=cik,
            ticker=company_info.get("ticker", f"CIK{cik}"),
            name=company_info.get("name", company_name),
            legal_name=company_info.get("name", company_name),
            sic=company_info.get("sic"),
            sic_description=company_info.get("sic_description"),
            is_active=True,
            is_sp500=is_sp500  # Only true if in our S&P 500 list
        )
        
        db.add(company)
        db.flush()  # Get the ID without committing
        
        return company
    
    def _create_filing_record(self, company_id: int, rss_filing: Dict) -> Filing:
        """
        Create a new filing record from RSS data
        
        Args:
            company_id: Company database ID
            rss_filing: Filing data from RSS
            
        Returns:
            Filing object
        """
        # Map form type
        form_mapping = {
            "10-K": FilingType.FORM_10K,
            "10-Q": FilingType.FORM_10Q,
            "8-K": FilingType.FORM_8K,
            "S-1": FilingType.FORM_S1
        }
        
        # Parse filing date
        filing_date = datetime.strptime(
            rss_filing["filing_date"], "%Y-%m-%d"
        )
        
        # Build primary document URL (will be updated when we fetch details)
        acc_no_clean = rss_filing["accession_number"].replace("-", "")
        primary_doc_url = (
            f"{settings.SEC_ARCHIVE_URL}/{rss_filing['cik']}/"
            f"{acc_no_clean}/index.htm"
        )
        
        return Filing(
            company_id=company_id,
            accession_number=rss_filing["accession_number"],
            filing_type=form_mapping.get(rss_filing["form"], FilingType.FORM_10K),
            filing_date=filing_date,
            primary_doc_url=primary_doc_url,
            full_text_url=rss_filing.get("rss_link", ""),
            status=ProcessingStatus.PENDING
        )
    
    def is_sp500_company(self, cik: str) -> bool:
        """
        Check if CIK belongs to S&P 500 company
        
        Args:
            cik: Company CIK
            
        Returns:
            True if S&P 500 company
        """
        return cik in self.sp500_ciks
    
    async def get_sp500_stats(self) -> Dict:
        """Get statistics about S&P 500 monitoring"""
        return {
            "total_sp500_companies": len(self.sp500_companies),
            "monitoring_ciks": len(self.sp500_ciks),
            "sample_companies": [
                f"{c['ticker']} ({c['name']})" 
                for c in self.sp500_companies[:5]
            ]
        }


# Debug: Print when module is imported
logger.info("=== EDGAR Scanner module loading ===")

# Create singleton instance
edgar_scanner = EDGARScanner()

logger.info(f"=== EDGAR Scanner initialized with {len(edgar_scanner.sp500_ciks)} S&P 500 companies ===")
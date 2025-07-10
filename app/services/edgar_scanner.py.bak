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
        
        # NEW: Load all monitored CIKs from database (S&P 500 + NASDAQ 100)
        self.monitored_ciks = self._load_monitored_ciks()
        
        # Debug output
        if self.monitored_ciks:
            logger.info(f"✅ Loaded {len(self.monitored_ciks)} companies for monitoring (S&P 500 + NASDAQ 100)")
            # Show breakdown
            sp500_only = len(self.sp500_ciks)
            total = len(self.monitored_ciks)
            logger.info(f"   - S&P 500 from JSON: {sp500_only}")
            logger.info(f"   - Total monitored (including NASDAQ 100): {total}")
            logger.info(f"   - Additional from database: {total - sp500_only}")
            # Show sample CIKs
            sample = list(self.monitored_ciks)[:5]
            logger.info(f"Sample monitored CIKs: {sample}")
        else:
            logger.error("❌ No companies loaded for monitoring!")
    
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
    
    def _load_monitored_ciks(self) -> set:
        """Load all CIKs we should monitor (S&P 500 + NASDAQ 100)"""
        monitored = set()
        
        # Add S&P 500 CIKs from JSON
        monitored.update(self.sp500_ciks)
        
        # Add NASDAQ 100 CIKs from database
        db = SessionLocal()
        try:
            # Get all companies that are either S&P 500 or NASDAQ 100
            companies = db.query(Company).filter(
                (Company.is_sp500 == True) | (Company.is_nasdaq100 == True)
            ).all()
            
            for company in companies:
                if company.cik and company.cik != '0000000000' and not company.cik.startswith('N'):
                    # Only add valid CIKs (not placeholders)
                    monitored.add(company.cik)
            
            logger.info(f"Loaded {len(companies)} companies from database (S&P 500 + NASDAQ 100)")
            
            # Show some NASDAQ 100 examples
            nasdaq_only = db.query(Company).filter(
                Company.is_sp500 == False,
                Company.is_nasdaq100 == True
            ).limit(5).all()
            
            if nasdaq_only:
                logger.info("Sample NASDAQ 100 (non-S&P 500) companies:")
                for company in nasdaq_only:
                    logger.info(f"   - {company.ticker}: {company.name} (CIK: {company.cik})")
            
        except Exception as e:
            logger.error(f"Error loading companies from database: {e}")
            logger.info("Falling back to S&P 500 only")
        finally:
            db.close()
        
        return monitored
        
    async def scan_for_new_filings(self) -> List[Dict]:
        """
        Main scanning method - uses RSS for efficiency
        
        Returns:
            List of new filings discovered
        """
        logger.info("Starting EDGAR RSS scan...")
        logger.info(f"DEBUG: Monitoring {len(self.monitored_ciks)} companies (S&P 500 + NASDAQ 100)")
        
        # Get recent filings from RSS (last 2 minutes to ensure overlap)
        all_rss_filings = await sec_client.get_rss_filings(
            form_type="all",
            lookback_minutes=60  # 或者 120，看更长时间范围
)
        
        if not all_rss_filings:
            logger.info("No new filings found in RSS feed")
            return []
        
        # Filter for monitored companies (S&P 500 + NASDAQ 100)
        relevant_filings = []
        for f in all_rss_filings:
            # S-1 filings (IPOs) are not limited to our indices
            if f['form'] == 'S-1':
                relevant_filings.append(f)
                logger.info(f"Including S-1 filing from {f.get('company_name', 'Unknown')} (CIK: {f['cik']})")
            # Check if CIK is in our monitored list
            elif f['cik'] in self.monitored_ciks:
                relevant_filings.append(f)
        
        logger.info(f"Found {len(relevant_filings)} relevant filings out of {len(all_rss_filings)} total")
        
        # Log some examples if we found filings
        if relevant_filings:
            for filing in relevant_filings[:3]:  # Show first 3
                if filing['form'] == 'S-1':
                    logger.info(f"IPO filing: {filing.get('company_name', 'Unknown')} - S-1 ({filing['filing_date']})")
                else:
                    # Try to find company in database for better info
                    db = SessionLocal()
                    try:
                        company = db.query(Company).filter(Company.cik == filing['cik']).first()
                        if company:
                            indices = company.indices or "Unknown"
                            logger.info(f"{indices} filing: {company.ticker} - {filing['form']} ({filing['filing_date']})")
                        else:
                            logger.info(f"Filing: {filing.get('company_name', 'Unknown')} - {filing['form']} ({filing['filing_date']})")
                    finally:
                        db.close()
        
        # Process each filing
        new_filings = []
        db = SessionLocal()
        
        try:
            for rss_filing in relevant_filings:
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
                    "discovery_method": "RSS",
                    "indices": company.indices  # Include index info
                })
                
                logger.info(
                    f"New filing discovered: {company.ticker} ({company.indices}) - {rss_filing['form']} "
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
        
        # Look up company in our S&P 500 list first
        sp500_company = next((c for c in self.sp500_companies if c['cik'] == cik), None)
        
        if sp500_company:
            # Use S&P 500 data
            company_info = {
                "cik": cik,
                "name": sp500_company['name'],
                "ticker": sp500_company['ticker']
            }
            is_sp500 = True
            is_nasdaq100 = False  # Will be updated if also in NASDAQ 100
        else:
            # Fetch from SEC API as fallback
            company_info = await sec_client.get_company_info(cik)
            if not company_info:
                logger.warning(f"Could not fetch info for CIK {cik}")
                company_info = {
                    "cik": cik,
                    "name": company_name,
                    "ticker": f"CIK{cik}"
                }
            is_sp500 = False
            is_nasdaq100 = False
        
        # Create new company record
        company = Company(
            cik=cik,
            ticker=company_info.get("ticker", f"CIK{cik}"),
            name=company_info.get("name", company_name),
            legal_name=company_info.get("name", company_name),
            sic=company_info.get("sic"),
            sic_description=company_info.get("sic_description"),
            is_active=True,
            is_sp500=is_sp500,
            is_nasdaq100=is_nasdaq100
        )
        
        # Update indices field
        company.update_indices()
        
        db.add(company)
        db.flush()  # Get the ID without committing
        
        logger.info(f"Created new company: {company.ticker} - {company.name} ({company.indices})")
        
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
    
    def is_monitored_company(self, cik: str) -> bool:
        """
        Check if CIK belongs to a monitored company (S&P 500 or NASDAQ 100)
        
        Args:
            cik: Company CIK
            
        Returns:
            True if monitored company
        """
        return cik in self.monitored_ciks
    
    def is_sp500_company(self, cik: str) -> bool:
        """
        Check if CIK belongs to S&P 500 company
        
        Args:
            cik: Company CIK
            
        Returns:
            True if S&P 500 company
        """
        return cik in self.sp500_ciks
    
    async def get_monitoring_stats(self) -> Dict:
        """Get statistics about monitored companies"""
        db = SessionLocal()
        try:
            sp500_count = db.query(Company).filter(Company.is_sp500 == True).count()
            nasdaq100_count = db.query(Company).filter(Company.is_nasdaq100 == True).count()
            both_count = db.query(Company).filter(
                Company.is_sp500 == True,
                Company.is_nasdaq100 == True
            ).count()
            
            return {
                "total_monitored": len(self.monitored_ciks),
                "sp500_companies": sp500_count,
                "nasdaq100_companies": nasdaq100_count,
                "both_indices": both_count,
                "sp500_only": sp500_count - both_count,
                "nasdaq100_only": nasdaq100_count - both_count,
                "sample_companies": [
                    f"{c['ticker']} ({c['name']})" 
                    for c in self.sp500_companies[:5]
                ]
            }
        finally:
            db.close()


# Debug: Print when module is imported
logger.info("=== EDGAR Scanner module loading ===")

# Create singleton instance
edgar_scanner = EDGARScanner()

logger.info(f"=== EDGAR Scanner initialized with {len(edgar_scanner.monitored_ciks)} monitored companies ===")
# app/services/edgar_scanner.py
"""
EDGAR Scanner Service - Enhanced with ticker management
FIXED: 
1. Ensure ticker is populated when creating filing records
2. Use lowercase status values consistently
3. Better validation before creating filing records
4. Auto-populate ticker from company relationship
ENHANCED: Record precise detection timestamps (detected_at field)
ENHANCED: Consistent timezone handling and validation
"""
from typing import List, Dict
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
import logging
import json
from pathlib import Path
import re

from app.services.sec_client import sec_client
from app.models.company import Company
from app.models.filing import Filing, FilingType, ProcessingStatus
from app.core.database import SessionLocal
from app.core.config import settings
from app.tasks.filing_tasks import process_filing_task

logger = logging.getLogger(__name__)


class EDGARScanner:
    """
    Scans SEC EDGAR for new filings using RSS feeds
    ENHANCED: Better ticker management and validation, precise detection timestamps
    """
    
    def __init__(self):
        self.scan_interval_minutes = 1  # Check RSS every minute
        self.supported_forms = ["10-K", "10-Q", "8-K", "S-1"]
        
        # Load S&P 500 companies from JSON file
        self.sp500_companies = self._load_sp500_companies()
        self.sp500_ciks = {company['cik'] for company in self.sp500_companies}
        
        # Load all monitored CIKs from database (S&P 500 + NASDAQ 100)
        self.monitored_ciks = self._load_monitored_ciks()
        
        # Debug output
        if self.monitored_ciks:
            logger.info(f"✅ Loaded {len(self.monitored_ciks)} companies for monitoring (S&P 500 + NASDAQ 100)")
            sp500_only = len(self.sp500_ciks)
            total = len(self.monitored_ciks)
            logger.info(f"   - S&P 500 from JSON: {sp500_only}")
            logger.info(f"   - Total monitored (including NASDAQ 100): {total}")
            logger.info(f"   - Additional from database: {total - sp500_only}")
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
    
    def _validate_filing_data(self, filing_data: Dict) -> bool:
        """
        Validate filing data before creating record
        Prevents empty filing records from being created
        """
        # Check required fields
        required_fields = ['accession_number', 'cik', 'form', 'filing_date']
        for field in required_fields:
            if not filing_data.get(field):
                logger.warning(f"Filing missing required field: {field}")
                return False
        
        # Validate accession number format (should be like 0000037996-25-000141)
        accession = filing_data.get('accession_number', '')
        if not re.match(r'^\d{10}-\d{2}-\d{6}$', accession):
            logger.warning(f"Invalid accession number format: {accession}")
            return False
        
        # Validate CIK (should be numeric)
        cik = filing_data.get('cik', '')
        if not cik.isdigit() or len(cik) > 10:
            logger.warning(f"Invalid CIK format: {cik}")
            return False
        
        # Validate form type
        form_type = filing_data.get('form', '')
        if form_type not in self.supported_forms:
            logger.warning(f"Unsupported form type: {form_type}")
            return False
        
        # Validate filing date
        try:
            datetime.strptime(filing_data['filing_date'], '%Y-%m-%d')
        except:
            logger.warning(f"Invalid filing date format: {filing_data.get('filing_date')}")
            return False
        
        return True
        
    async def scan_for_new_filings(self) -> List[Dict]:
        """
        Main scanning method - uses RSS for efficiency
        ENHANCED: Records precise detection timestamps with timezone handling
        
        Returns:
            List of new filings discovered
        """
        logger.info("Starting EDGAR RSS scan...")
        logger.info(f"DEBUG: Monitoring {len(self.monitored_ciks)} companies (S&P 500 + NASDAQ 100)")
        
        # ENHANCED: Record the precise scan time in UTC - this will be our detection timestamp
        scan_start_time = datetime.now(timezone.utc)
        logger.debug(f"Scan started at: {scan_start_time.isoformat()}")
        
        # Get recent filings from RSS (last 60 minutes to ensure overlap)
        all_rss_filings = await sec_client.get_rss_filings(
            form_type="all",
            lookback_minutes=60
        )
        
        if not all_rss_filings:
            logger.info("No new filings found in RSS feed")
            return []
        
        # Filter for monitored companies (S&P 500 + NASDAQ 100)
        relevant_filings = []
        for f in all_rss_filings:
            # Validate filing data first
            if not self._validate_filing_data(f):
                logger.warning(f"Skipping invalid filing entry from {f.get('company_name', 'Unknown')}")
                continue
                
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
        
        # Process each filing in its own transaction
        for rss_filing in relevant_filings:
            db = SessionLocal()
            try:
                # Check if we already have this filing
                existing = db.query(Filing).filter(
                    Filing.accession_number == rss_filing["accession_number"]
                ).first()
                
                if existing:
                    logger.debug(f"Filing {rss_filing['accession_number']} already exists")
                    # ENHANCED: Ensure ticker is populated even for existing filings
                    if existing and not existing.ticker and existing.company:
                        existing.ticker = existing.company.ticker
                        db.commit()
                    # ENHANCED: Update detected_at if missing (for old records)
                    if existing and not existing.detected_at:
                        existing.detected_at = scan_start_time
                        logger.debug(f"Updated detected_at for existing filing {existing.id}")
                        db.commit()
                    continue
                
                # Get or create company
                company = await self._get_or_create_company(
                    db, rss_filing["cik"], rss_filing.get("company_name", "")
                )
                
                if not company:
                    logger.warning(f"Could not find/create company for CIK {rss_filing['cik']}")
                    continue
                
                # Additional validation before creating filing
                if not self._validate_before_creation(rss_filing, company):
                    logger.warning(f"Skipping filing creation for {company.ticker} - failed pre-creation validation")
                    continue
                
                # ENHANCED: Create new filing record with precise detection time
                filing = self._create_filing_record(company, rss_filing, scan_start_time)
                db.add(filing)
                
                # Commit immediately to make filing available to other processes
                db.commit()
                
                # Now the filing is persisted and has an ID
                filing_id = filing.id
                
                new_filings.append({
                    "id": filing_id,
                    "company": company.name,
                    "ticker": filing.ticker or company.ticker,  # Use filing ticker or company ticker
                    "form_type": rss_filing["form"],
                    "filing_date": rss_filing["filing_date"],
                    "detected_at": scan_start_time.isoformat(),  # ENHANCED: Include detection time
                    "accession_number": rss_filing["accession_number"],
                    "discovery_method": "RSS",
                    "indices": company.indices
                })
                
                logger.info(
                    f"New filing discovered: {filing.ticker or company.ticker} ({company.indices}) - {rss_filing['form']} "
                    f"({rss_filing['filing_date']}) detected at {scan_start_time.strftime('%H:%M:%S')} UTC - Filing ID: {filing_id}"
                )
                
                # Automatically trigger Celery task to process this filing
                try:
                    # Queue the filing for processing
                    task = process_filing_task.delay(filing_id)
                    
                    logger.info(
                        f"✅ Queued filing {filing_id} for processing. "
                        f"Celery task ID: {task.id}"
                    )
                    
                except Exception as e:
                    logger.error(f"❌ Failed to queue filing {filing_id} for processing: {e}")
                    # Continue even if queueing fails - filing is still saved
                    
            except Exception as e:
                logger.error(f"Error processing filing {rss_filing.get('accession_number', 'unknown')}: {e}")
                db.rollback()
                # Continue with next filing
            finally:
                db.close()
        
        logger.info(f"Successfully processed {len(new_filings)} new filings")
        
        # ENHANCED: Update any filings with missing tickers or timestamps
        self._update_missing_data()
        
        return new_filings
    
    def _validate_before_creation(self, rss_filing: Dict, company: Company) -> bool:
        """
        Additional validation before creating filing record
        ENHANCED: Timezone-aware validation
        """
        # Don't create filings for inactive companies
        if not company.is_active:
            logger.warning(f"Company {company.ticker} is marked inactive")
            return False
        
        # ENHANCED: Verify the filing date is reasonable (not too far in the future)
        filing_date = datetime.strptime(rss_filing['filing_date'], '%Y-%m-%d')
        filing_date_utc = filing_date.replace(tzinfo=timezone.utc)
        current_time_utc = datetime.now(timezone.utc)
        
        # Allow up to 1 day in the future (for timezone differences)
        if filing_date_utc > current_time_utc + timedelta(days=1):
            logger.warning(f"Filing date {filing_date_utc} is too far in the future")
            return False
        
        # Check if we have a valid document URL or can construct one
        if not rss_filing.get('rss_link') and not rss_filing.get('accession_number'):
            logger.warning("No valid document URL or accession number")
            return False
        
        return True
    
    async def _get_or_create_company(self, db: Session, cik: str, company_name: str = "") -> Company:
        """
        Get company from database or create if doesn't exist
        ENHANCED: Ensure ticker is populated
        
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
            # ENHANCED: Update filings with missing tickers if company has ticker
            if company.ticker:
                company.update_filings_ticker(db)
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
                # For S-1 filings without ticker, use company name as temporary identifier
                company_info = {
                    "cik": cik,
                    "name": company_name,
                    "ticker": None  # Allow NULL for S-1 filings
                }
            is_sp500 = False
            is_nasdaq100 = False
        
        # Create new company record
        company = Company(
            cik=cik,
            ticker=company_info.get("ticker"),  # Can be NULL for S-1
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
        
        logger.info(f"Created new company: {company.ticker or 'NO_TICKER'} - {company.name} ({company.indices})")
        
        return company
    
    def _create_filing_record(self, company: Company, rss_filing: Dict, detection_time: datetime) -> Filing:
        """
        Create a new filing record from RSS data
        ENHANCED: Records precise detection timestamp and ensures ticker is populated
        ENHANCED: Consistent timezone handling
        
        Args:
            company: Company object
            rss_filing: RSS filing data
            detection_time: Precise UTC timestamp when filing was detected
        """
        # Map form type
        form_mapping = {
            "10-K": FilingType.FORM_10K,
            "10-Q": FilingType.FORM_10Q,
            "8-K": FilingType.FORM_8K,
            "S-1": FilingType.FORM_S1
        }
        
        # ENHANCED: Parse filing date and make it timezone-aware (UTC)
        filing_date = datetime.strptime(
            rss_filing["filing_date"], "%Y-%m-%d"
        )
        # Store as UTC timezone-aware datetime
        filing_date_utc = filing_date.replace(tzinfo=timezone.utc)
        
        # ENHANCED: Ensure detection_time is timezone-aware UTC
        if detection_time.tzinfo is None:
            detection_time = detection_time.replace(tzinfo=timezone.utc)
        elif detection_time.tzinfo != timezone.utc:
            detection_time = detection_time.astimezone(timezone.utc)
        
        # ENHANCED: Create Filing with ticker from company and precise detection time
        filing = Filing(
            company_id=company.id,
            ticker=company.ticker,  # Set ticker from company
            accession_number=rss_filing["accession_number"],
            filing_type=form_mapping.get(rss_filing["form"], FilingType.FORM_10K),
            form_type=rss_filing["form"],  # Store raw form type too
            filing_date=filing_date_utc,  # Official SEC filing date (UTC)
            detected_at=detection_time,  # ENHANCED: When we detected this filing (precise UTC timestamp)
            status=ProcessingStatus.PENDING  # Using enum value
        )
        
        # Set URL fields as attributes after creation
        if rss_filing.get('rss_link'):
            filing.filing_url = rss_filing['rss_link']
            filing.full_text_url = rss_filing['rss_link']
            filing.primary_document_url = rss_filing['rss_link']
        
        # Ensure ticker is populated
        if not filing.ticker and company.ticker:
            filing.ticker = company.ticker
        
        # Log the creation with timing info
        logger.debug(f"Created filing record: {filing.ticker} {filing.filing_type.value} "
                    f"filed={filing_date_utc.isoformat()} detected={detection_time.isoformat()}")
        
        return filing
    
    def _update_missing_data(self):
        """
        ENHANCED: Update all filings with missing tickers or timestamps
        Run periodically to fix any filings that don't have complete data
        """
        db = SessionLocal()
        try:
            # ENHANCED: Find filings with missing tickers OR missing detected_at
            filings_needing_update = db.query(Filing).filter(
                (Filing.ticker == None) | (Filing.ticker == '') | (Filing.detected_at == None)
            ).all()
            
            if filings_needing_update:
                logger.info(f"Found {len(filings_needing_update)} filings needing data updates")
                
                updated_ticker_count = 0
                updated_timestamp_count = 0
                
                for filing in filings_needing_update:
                    # Update missing ticker
                    if (not filing.ticker or filing.ticker == '') and filing.company and filing.company.ticker:
                        filing.ticker = filing.company.ticker
                        updated_ticker_count += 1
                    
                    # Update missing detected_at (use created_at as fallback)
                    if not filing.detected_at and filing.created_at:
                        filing.detected_at = filing.created_at
                        updated_timestamp_count += 1
                        logger.debug(f"Set detected_at={filing.created_at.isoformat()} for filing {filing.id}")
                
                if updated_ticker_count > 0 or updated_timestamp_count > 0:
                    db.commit()
                    logger.info(f"Updated {updated_ticker_count} tickers and {updated_timestamp_count} timestamps")
                    
        except Exception as e:
            logger.error(f"Error updating missing data: {e}")
            db.rollback()
        finally:
            db.close()
    
    def is_monitored_company(self, cik: str) -> bool:
        """Check if CIK belongs to a monitored company (S&P 500 or NASDAQ 100)"""
        return cik in self.monitored_ciks
    
    def is_sp500_company(self, cik: str) -> bool:
        """Check if CIK belongs to S&P 500 company"""
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
    
    def get_sp500_stats(self) -> Dict:
        """
        Get statistics for S&P 500 and NASDAQ 100 companies
        Used for health checks and monitoring
        ENHANCED: Include detected_at timing information
        """
        db = SessionLocal()
        try:
            # Get various statistics
            sp500_count = db.query(Company).filter(Company.is_sp500 == True).count()
            nasdaq100_count = db.query(Company).filter(Company.is_nasdaq100 == True).count()
            both_count = db.query(Company).filter(
                Company.is_sp500 == True,
                Company.is_nasdaq100 == True
            ).count()
            
            # ENHANCED: Get today's filings using detected_at when available
            today_start_utc = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            
            # Count filings detected today (prioritize detected_at over filing_date)
            today_filings = db.query(Filing).filter(
                (Filing.detected_at >= today_start_utc) | 
                ((Filing.detected_at == None) & (Filing.filing_date >= today_start_utc))
            ).count()
            
            # Get pending filings count
            pending_filings = db.query(Filing).filter(
                Filing.status == ProcessingStatus.PENDING
            ).count()
            
            # ENHANCED: Get latest filing using detected_at first, then created_at
            latest_filing = db.query(Filing).order_by(
                Filing.detected_at.desc().nulls_last(),  # detected_at first (nulls last)
                Filing.created_at.desc()  # created_at as fallback
            ).first()
            
            latest_filing_info = None
            if latest_filing:
                company = db.query(Company).filter(
                    Company.id == latest_filing.company_id
                ).first()
                if company:
                    # Use detected_at if available, otherwise created_at
                    time_ref = latest_filing.detected_at or latest_filing.created_at
                    detection_time = time_ref.strftime('%H:%M UTC') if time_ref else 'Unknown'
                    time_type = 'detected' if latest_filing.detected_at else 'created'
                    latest_filing_info = f"{company.ticker or latest_filing.ticker} - {latest_filing.filing_type.value} ({time_type} {detection_time})"
            
            # ENHANCED: Get filings without detected_at (for health monitoring)
            filings_without_detected_at = db.query(Filing).filter(
                Filing.detected_at == None
            ).count()
            
            return {
                'total_monitored': len(self.monitored_ciks),
                'sp500_companies': sp500_count,
                'nasdaq100_companies': nasdaq100_count,
                'both_indices': both_count,
                'sp500_only': sp500_count - both_count,
                'nasdaq100_only': nasdaq100_count - both_count,
                'today_filings': today_filings,
                'pending_filings': pending_filings,
                'latest_filing': latest_filing_info,
                'filings_without_detected_at': filings_without_detected_at,
                'status': 'active',
                'last_check': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting S&P 500 stats: {e}")
            return {
                'total_monitored': len(self.monitored_ciks) if self.monitored_ciks else 0,
                'sp500_companies': len(self.sp500_companies) if self.sp500_companies else 0,
                'nasdaq100_companies': 0,
                'both_indices': 0,
                'sp500_only': 0,
                'nasdaq100_only': 0,
                'today_filings': 0,
                'pending_filings': 0,
                'latest_filing': None,
                'filings_without_detected_at': 0,
                'status': 'initializing',
                'error': str(e)
            }
        finally:
            db.close()


# Debug: Print when module is imported
logger.info("=== EDGAR Scanner module loading ===")

# Create singleton instance
edgar_scanner = EDGARScanner()

logger.info(f"=== EDGAR Scanner initialized with {len(edgar_scanner.monitored_ciks)} monitored companies ===")
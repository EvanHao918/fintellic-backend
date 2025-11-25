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
from typing import List, Dict, Optional
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


class SmartLogger:
    """
    Smart logging helper that reduces log noise while maintaining observability
    - Logs important events immediately (new filings found)
    - Logs periodic health checks (hourly)
    - Suppresses repetitive "no new data" messages
    """
    def __init__(self):
        self.last_hourly_log = None
        self.session_start = datetime.now(timezone.utc)
        self.total_scans = 0
        self.total_filings_found = 0
    
    def should_log_hourly_check(self) -> bool:
        """Check if we should log hourly health check"""
        now = datetime.now(timezone.utc)
        if self.last_hourly_log is None:
            return True
        
        # Log once per hour, at the top of the hour (first scan after XX:00)
        time_since_last = now - self.last_hourly_log
        return time_since_last >= timedelta(hours=1) and now.minute < 5
    
    def log_scan_result(self, filings_found: int, companies_monitored: int):
        """Log scan result with smart filtering"""
        self.total_scans += 1
        self.total_filings_found += filings_found
        
        if filings_found > 0:
            # Always log when new filings are found
            logger.info(f"🎯 Found {filings_found} new filings! Total monitored companies: {companies_monitored}")
        elif self.should_log_hourly_check():
            # Periodic health check
            uptime = datetime.now(timezone.utc) - self.session_start
            hours = int(uptime.total_seconds() / 3600)
            logger.info(
                f"✅ Hourly health check - System running normally | "
                f"Uptime: {hours}h | Scans: {self.total_scans} | "
                f"Total filings found: {self.total_filings_found} | "
                f"Monitoring: {companies_monitored} companies"
            )
            self.last_hourly_log = datetime.now(timezone.utc)
        # Else: Silent operation - no logs for "no new data" scans


# Global smart logger instance
smart_logger = SmartLogger()


class EDGARScanner:
    """
    Scans SEC EDGAR for new filings
    
    Data Source Strategy (v2):
    - JSON submissions API: For 8-K/10-Q/10-K (known CIKs, 100% reliable)
    - RSS feed: Only for S-1 (IPO filings from unknown CIKs)
    
    ENHANCED: Better ticker management, precise detection timestamps, hourly summary logs
    """
    
    def __init__(self):
        self.scan_interval_seconds = 70  # JSON scan interval (was 60s for RSS)
        self.supported_forms = ["10-K", "10-Q", "8-K", "S-1"]
        self.json_forms = {"10-K", "10-Q", "8-K"}  # Forms using JSON API
        self.rss_forms = {"S-1"}  # Forms using RSS (unknown CIKs)
        
        # Load S&P 500 companies from JSON file
        self.sp500_companies = self._load_sp500_companies()
        self.sp500_ciks = {company['cik'] for company in self.sp500_companies}
        
        # Load NASDAQ 100 companies from JSON file
        self.nasdaq100_companies = self._load_nasdaq100_companies()
        self.nasdaq100_ciks = {company['cik'] for company in self.nasdaq100_companies}
        
        # Combined monitored CIKs (for JSON scanning)
        self.monitored_ciks = self.sp500_ciks | self.nasdaq100_ciks
        
        # Hourly summary tracking
        self.hourly_filings = []  # Filings found in current hour
        self.last_hourly_summary = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        
        # Log initialization
        if self.monitored_ciks:
            logger.info(
                f"📊 Scanner initialized (v2 JSON+RSS): "
                f"{len(self.monitored_ciks)} CIKs | "
                f"JSON: 8-K/10-Q/10-K | RSS: S-1 | "
                f"Interval: {self.scan_interval_seconds}s"
            )
        else:
            logger.error("❌ No companies loaded for monitoring!")
    
    def _load_sp500_companies(self) -> list:
        """Load S&P 500 companies from JSON file"""
        json_path = Path(__file__).parent.parent / "data" / "sp500_companies.json"
        
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
                companies = data.get('companies', [])
                logger.info(f"Loaded {len(companies)} S&P 500 companies")
                return companies
        except FileNotFoundError:
            logger.error(f"S&P 500 companies file not found at {json_path}")
            return []
        except Exception as e:
            logger.error(f"Error loading S&P 500 companies: {e}")
            return []
    
    def _load_nasdaq100_companies(self) -> list:
        """Load NASDAQ 100 companies from JSON file"""
        json_path = Path(__file__).parent.parent / "data" / "nasdaq100_companies.json"
        
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
                companies = data.get('companies', [])
                logger.info(f"Loaded {len(companies)} NASDAQ 100 companies")
                return companies
        except FileNotFoundError:
            logger.error(f"NASDAQ 100 companies file not found at {json_path}")
            return []
        except Exception as e:
            logger.error(f"Error loading NASDAQ 100 companies: {e}")
            return []
    
    def _get_known_accessions(self) -> set:
        """Get all accession numbers already in database"""
        db = SessionLocal()
        try:
            accessions = db.query(Filing.accession_number).all()
            return {a[0] for a in accessions if a[0]}
        except Exception as e:
            logger.error(f"Error loading known accessions: {e}")
            return set()
        finally:
            db.close()
    
    def _check_hourly_summary(self):
        """Output hourly summary if hour has changed"""
        now = datetime.now(timezone.utc)
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        
        if current_hour > self.last_hourly_summary:
            # Hour changed, output summary
            if self.hourly_filings:
                summary_lines = [f"{f['ticker']} {f['form']} ({f['time']})" for f in self.hourly_filings]
                logger.info(
                    f"📊 Hourly Summary ({self.last_hourly_summary.strftime('%H:00')}-{current_hour.strftime('%H:00')} UTC): "
                    f"{len(self.hourly_filings)} filings | {', '.join(summary_lines)}"
                )
            else:
                logger.info(
                    f"📊 Hourly Summary ({self.last_hourly_summary.strftime('%H:00')}-{current_hour.strftime('%H:00')} UTC): "
                    f"No new filings"
                )
            
            # Reset for new hour
            self.hourly_filings = []
            self.last_hourly_summary = current_hour
    
    def _add_to_hourly_summary(self, ticker: str, form: str, time_str: str):
        """Add filing to hourly summary tracking"""
        self.hourly_filings.append({
            "ticker": ticker,
            "form": form,
            "time": time_str
        })
    
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
    
    def _extract_items_from_rss(self, filing_data: Dict) -> List[str]:
        """
        从 RSS filing data 中提取官方 SEC Item 编号
        
        Args:
            filing_data: RSS entry 的字典数据
            
        Returns:
            List of Item numbers (e.g., ["2.03", "9.01"])
        """
        # RSS feed 中的 items 字段
        items_str = filing_data.get('items', '')
        
        if not items_str or items_str.strip() == '':
            return []
        
        # 可能是 "2.03" 或 "2.03, 9.01" 格式
        items = [item.strip() for item in items_str.split(',')]
        
        # 过滤掉空字符串和无效格式
        valid_items = []
        for item in items:
            # 验证格式：应该是 X.XX 格式
            if re.match(r'^\d+\.\d{2}$', item):
                valid_items.append(item)
            else:
                logger.debug(f"Skipping invalid item format: {item}")
        
        if valid_items:
            logger.debug(f"Extracted Items from RSS: {valid_items}")
        
        return valid_items
        
    async def scan_for_new_filings(self) -> List[Dict]:
        """
        Main scanning method (v2)
        
        Data Source Strategy:
        - JSON submissions API: For 8-K/10-Q/10-K (known CIKs, 100% reliable)
        - RSS feed: Only for S-1 (IPO filings from unknown CIKs)
        
        Returns:
            List of new filings discovered
        """
        scan_start_time = datetime.now(timezone.utc)
        
        # Check if we need to output hourly summary
        self._check_hourly_summary()
        
        all_new_filings = []
        
        # ==================== PART 1: JSON Scan (8-K/10-Q/10-K) ====================
        # Get known accession numbers to filter out duplicates
        known_accessions = self._get_known_accessions()
        
        # Batch query all monitored CIKs
        json_result = await sec_client.get_batch_submissions(
            ciks=list(self.monitored_ciks),
            known_accessions=known_accessions
        )
        
        # Process new filings from JSON
        for filing_data in json_result.get("new_filings", []):
            new_filing = await self._process_new_filing(
                filing_data=filing_data,
                scan_start_time=scan_start_time,
                discovery_method="JSON"
            )
            if new_filing:
                all_new_filings.append(new_filing)
        
        # ==================== PART 2: RSS Scan (S-1 only) ====================
        s1_filings = await sec_client.get_rss_filings(
            form_type="S-1",
            lookback_minutes=60
        )
        
        # Process S-1 filings
        for rss_filing in s1_filings:
            if not self._validate_filing_data(rss_filing):
                continue
            
            # Check if already exists
            if rss_filing.get("accession_number") in known_accessions:
                continue
            
            new_filing = await self._process_new_filing(
                filing_data=rss_filing,
                scan_start_time=scan_start_time,
                discovery_method="RSS"
            )
            if new_filing:
                all_new_filings.append(new_filing)
        
        # Log scan summary
        smart_logger.log_scan_result(len(all_new_filings), len(self.monitored_ciks))
        
        return all_new_filings
    
    async def _process_new_filing(self, filing_data: Dict, scan_start_time: datetime, discovery_method: str) -> Optional[Dict]:
        """
        Process a single new filing - create record and queue for processing
        
        Args:
            filing_data: Filing data from JSON or RSS
            scan_start_time: When this scan started (for detected_at)
            discovery_method: "JSON" or "RSS"
            
        Returns:
            Filing info dict or None if failed
        """
        db = SessionLocal()
        try:
            # Check if already exists (double-check)
            existing = db.query(Filing).filter(
                Filing.accession_number == filing_data.get("accession_number")
            ).first()
            
            if existing:
                return None
            
            # Get or create company
            cik = filing_data.get("cik", "")
            company_name = filing_data.get("company_name", "")
            company = await self._get_or_create_company(db, cik, company_name)
            
            if not company:
                logger.warning(f"Could not find/create company for CIK {cik}")
                return None
            
            # Validate before creation
            if not self._validate_before_creation(filing_data, company):
                return None
            
            # Create filing record
            filing = self._create_filing_record(company, filing_data, scan_start_time)
            db.add(filing)
            db.commit()
            
            filing_id = filing.id
            ticker = filing.ticker or company.ticker
            form_type = filing_data.get("form", "")
            
            # Add to hourly summary
            self._add_to_hourly_summary(
                ticker=ticker,
                form=form_type,
                time_str=scan_start_time.strftime("%H:%M")
            )
            
            # Log discovery
            logger.info(
                f"🎯 New {discovery_method}: {ticker} {form_type} "
                f"({filing_data.get('filing_date', 'N/A')}) - ID: {filing_id}"
            )
            
            # Queue for AI processing
            try:
                task = process_filing_task.delay(filing_id)
                logger.info(f"✅ Queued {filing_id} for processing (task: {task.id[:8]}...)")
            except Exception as e:
                logger.error(f"❌ Failed to queue filing {filing_id}: {e}")
            
            return {
                "id": filing_id,
                "company": company.name,
                "ticker": ticker,
                "form_type": form_type,
                "filing_date": filing_data.get("filing_date", ""),
                "detected_at": scan_start_time.isoformat(),
                "accession_number": filing_data.get("accession_number", ""),
                "discovery_method": discovery_method,
                "indices": getattr(company, 'indices', '')
            }
            
        except Exception as e:
            logger.error(f"Error processing filing {filing_data.get('accession_number', 'unknown')}: {e}")
            db.rollback()
            return None
        finally:
            db.close()
    
    def _validate_before_creation(self, filing_data: Dict, company: Company) -> bool:
        """
        Additional validation before creating filing record
        Works with both JSON and RSS data formats
        """
        # Don't create filings for inactive companies
        if not company.is_active:
            logger.warning(f"Company {company.ticker} is marked inactive")
            return False
        
        # Verify the filing date is reasonable (not too far in the future)
        filing_date = datetime.strptime(filing_data['filing_date'], '%Y-%m-%d')
        filing_date_utc = filing_date.replace(tzinfo=timezone.utc)
        current_time_utc = datetime.now(timezone.utc)
        
        # Allow up to 1 day in the future (for timezone differences)
        if filing_date_utc > current_time_utc + timedelta(days=1):
            logger.warning(f"Filing date {filing_date_utc} is too far in the future")
            return False
        
        # Check if we have a valid document URL or can construct one
        if not filing_data.get('rss_link') and not filing_data.get('accession_number'):
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
    
    def _create_filing_record(self, company: Company, filing_data: Dict, detection_time: datetime) -> Filing:
        """
        Create a new filing record from JSON or RSS data
        
        Args:
            company: Company object
            filing_data: Filing data (from JSON submissions or RSS)
            detection_time: Precise UTC timestamp when filing was detected
        """
        # Map form type
        form_mapping = {
            "10-K": FilingType.FORM_10K,
            "10-Q": FilingType.FORM_10Q,
            "8-K": FilingType.FORM_8K,
            "S-1": FilingType.FORM_S1
        }
        
        # Parse filing date and make it timezone-aware (UTC)
        filing_date = datetime.strptime(
            filing_data["filing_date"], "%Y-%m-%d"
        )
        filing_date_utc = filing_date.replace(tzinfo=timezone.utc)
        
        # Ensure detection_time is timezone-aware UTC
        if detection_time.tzinfo is None:
            detection_time = detection_time.replace(tzinfo=timezone.utc)
        elif detection_time.tzinfo != timezone.utc:
            detection_time = detection_time.astimezone(timezone.utc)
        
        # Extract official SEC Item numbers for 8-K filings (RSS only)
        official_items = []
        if filing_data.get("form") == "8-K" and filing_data.get("rss_link"):
            official_items = self._extract_items_from_rss(filing_data)
            if official_items:
                logger.debug(f"8-K filing has official Items: {official_items}")
        
        # Create Filing with ticker from company and precise detection time
        filing = Filing(
            company_id=company.id,
            ticker=company.ticker,
            accession_number=filing_data["accession_number"],
            filing_type=form_mapping.get(filing_data.get("form", ""), FilingType.FORM_10K),
            form_type=filing_data.get("form", ""),
            filing_date=filing_date_utc,
            detected_at=detection_time,
            status=ProcessingStatus.PENDING,
            event_items=official_items if official_items else None
        )
        
        # Set URL fields - support both RSS (rss_link) and JSON (construct from accession)
        if filing_data.get('rss_link'):
            filing.filing_url = filing_data['rss_link']
            filing.full_text_url = filing_data['rss_link']
            filing.primary_document_url = filing_data['rss_link']
        elif filing_data.get('accession_number') and filing_data.get('cik'):
            # Construct URL for JSON-sourced filings
            cik = filing_data['cik'].lstrip('0')
            acc_no = filing_data['accession_number'].replace('-', '')
            base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no}"
            filing.filing_url = base_url
            if filing_data.get('primary_document'):
                filing.primary_document_url = f"{base_url}/{filing_data['primary_document']}"
        
        # Ensure ticker is populated
        if not filing.ticker and company.ticker:
            filing.ticker = company.ticker
        
        # Log the creation with timing info
        log_msg = f"Created filing record: {filing.ticker} {filing.filing_type.value} filed={filing_date_utc.isoformat()} detected={detection_time.isoformat()}"
        if official_items:
            log_msg += f" items={official_items}"
        logger.debug(log_msg)
        
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
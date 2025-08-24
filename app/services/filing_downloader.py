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

from app.models.filing import Filing, ProcessingStatus, FilingType
# Phase 4: 导入通知服务
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)


class FilingDownloader:
    """
    Enhanced filing downloader with comprehensive exhibit processing
    
    ENHANCED: 支持 Exhibit 99 + 10.x 系列的完整附件处理
    - Exhibit 99: 新闻稿、财务数据、投资者材料 (已有，保持不变)
    - Exhibit 10.1-10.9: 重大合同、供应商协议、客户合同
    - Exhibit 10.10+: 高管补偿、RSU协议、股票期权
    
    优化原则：
    1. 基于现有 _parse_exhibit_99_files 架构进行扩展
    2. 保持向后兼容，所有现有功能不变
    3. 统一处理逻辑，智能优先级分配
    4. 性能优化：文件大小限制、容错机制
    """
    
    def __init__(self):
        self.base_url = "https://www.sec.gov/Archives/edgar/data"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        self.rate_limit_delay = 0.1  # SEC rate limit
        self.last_request_time = datetime.now()
        self.data_dir = Path("data/filings")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 附件处理配置
        self.max_exhibit_file_size = 50 * 1024 * 1024  # 50MB limit per exhibit
        self.max_exhibits_per_filing = 20  # Maximum exhibits to download per filing
    
    async def _rate_limit(self):
        """Respect SEC rate limits"""
        now = datetime.now()
        time_since_last = (now - self.last_request_time).total_seconds()
        
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)
        
        self.last_request_time = datetime.now()
    
    def _get_filing_directory(self, filing: Filing) -> Path:
        """Get the local directory path for storing filing files"""
        acc_no_clean = filing.accession_number.replace("-", "")
        return self.data_dir / filing.company.cik / acc_no_clean
    
    def _extract_url_from_ixbrl_link(self, href: str) -> str:
        """
        Extract the actual document URL from iXBRL viewer link
        
        Example: /ix?doc=/Archives/edgar/data/37996/000003799625000141/f-20250716.htm
        Returns: /Archives/edgar/data/37996/000003799625000141/f-20250716.htm
        """
        if '/ix?doc=' in href:
            doc_start = href.find('doc=') + 4
            doc_end = href.find('&', doc_start) if '&' in href[doc_start:] else len(href)
            doc_path = href[doc_start:doc_end]
            return unquote(doc_path)
        return href
    
    def _is_ixbrl_viewer_page(self, content: str) -> bool:
        """
        Check if the content is an iXBRL viewer page
        These are 6.2KB JavaScript files that load the real document
        """
        sample = content[:2000] if len(content) > 2000 else content
        
        viewer_markers = [
            'loadViewer',
            'ixvFrame',
            'XBRL Viewer',
            'Created by staff of the U.S. Securities and Exchange Commission'
        ]
        
        return any(marker in sample for marker in viewer_markers)
    
    def _is_fee_calculation_table(self, filename: str, description: str = "") -> bool:
        """
        Check if a document is a fee calculation table (not the main S-1)
        Based on actual database patterns
        
        Returns True if this is a fee table that should be skipped
        """
        filename_lower = filename.lower()
        desc_lower = description.lower()
        
        # Fee calculation indicators based on real data
        fee_indicators = [
            'ex-fee',           # ea025217101ex-fee_seastar.htm
            'exfee',
            'ex_fee',
            'ex-filingfees',    # tm2521253d3_ex-filingfees.htm
            'exfilingfees',
            'filing-fees',
            'filingfees',
            'fee-table',
            'feetable',
            'ex107',            # ex107.htm (common exhibit for fees)
            'ex_107',
            'ex-107',
            'calculation'
        ]
        
        # Check filename
        for indicator in fee_indicators:
            if indicator in filename_lower:
                logger.debug(f"Identified fee calculation table by filename: {filename}")
                return True
        
        # Check if it's an exhibit (except for main S-1 exhibits)
        if re.match(r'^ex[_-]?\d+', filename_lower) and 's1' not in filename_lower:
            logger.debug(f"Identified exhibit file (likely fee table): {filename}")
            return True
        
        # Check description
        if description:
            if any(term in desc_lower for term in ['fee', 'calculation', 'exhibit 107', 'filing fee']):
                logger.debug(f"Identified fee table by description: {description}")
                return True
        
        return False
    
    def _is_main_s1_document(self, filename: str, doc_type: str = "", description: str = "") -> int:
        """
        Score a document to determine if it's likely the main S-1
        Based on actual successful patterns from database
        
        Returns a score (higher = more likely to be main S-1)
        """
        filename_lower = filename.lower()
        type_lower = doc_type.lower() if doc_type else ""
        desc_lower = description.lower() if description else ""
        
        score = 0
        
        # Positive patterns (from successful database examples)
        if 'forms-1.htm' == filename_lower:
            score += 100  # Most common successful pattern
        elif re.match(r'.*-s1[_.].*\.htm', filename_lower):
            score += 90   # ea0250754-s1_osthera.htm pattern
        elif re.match(r'd\d+s1\.htm', filename_lower):
            score += 90   # d941967ds1.htm pattern
        elif re.match(r'tm\d+.*s1\.htm', filename_lower):
            score += 85   # tm2521627-1_s1.htm pattern
        elif 's1' in filename_lower and not self._is_fee_calculation_table(filename):
            score += 50
        
        # Check document type
        if 's-1' in type_lower or 'registration' in type_lower:
            score += 30
        
        # Check description
        if 'registration statement' in desc_lower:
            score += 20
        elif 'main document' in desc_lower:
            score += 20
        
        # Negative patterns (penalize fee tables)
        if self._is_fee_calculation_table(filename, description):
            score -= 1000  # Heavily penalize fee tables
        
        return score
    
    def _parse_index_enhanced(self, html_content: str, filing_type: str) -> Optional[Dict]:
        """
        Enhanced index parser with S-1 specific logic
        Based on actual database patterns
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # For S-1 filings, use special logic
        if filing_type == FilingType.FORM_S1.value or filing_type == 'S-1':
            return self._parse_index_for_s1(soup)
        
        # For other filing types, use original logic
        return self._parse_index_generic(soup, filing_type)
    
    def _parse_index_for_s1(self, soup: BeautifulSoup) -> Optional[Dict]:
        """
        Special S-1 document detection based on database patterns
        Priority order:
        1. forms-1.htm (most common successful pattern)
        2. *-s1_*.htm patterns
        3. d*s1.htm patterns
        4. Other S-1 patterns
        
        Avoid:
        - ex-fee_* files
        - ex107.htm files
        - ex-filingfees files
        """
        candidates = []
        
        # Check all links in the page
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '')
            link_text = link.get_text(strip=True)
            
            # Get parent row for context (description, type)
            parent_row = link.find_parent('tr')
            row_text = parent_row.get_text() if parent_row else ""
            
            # Handle iXBRL links
            if '/ix?doc=' in href:
                actual_url = self._extract_url_from_ixbrl_link(href)
            else:
                actual_url = href
            
            filename = actual_url.split('/')[-1] if '/' in actual_url else actual_url
            
            # Skip if no filename
            if not filename:
                continue
            
            # Score this document
            score = self._is_main_s1_document(filename, row_text, link_text)
            
            if score > 0:
                candidates.append({
                    'filename': filename,
                    'url': actual_url,
                    'type': 'S-1',
                    'description': link_text or 'Registration Statement',
                    'score': score
                })
                logger.debug(f"S-1 candidate: {filename} (score: {score})")
        
        # Also check tables for structured data
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                
                if len(cells) < 3:
                    continue
                
                # Skip header rows
                row_text = ' '.join(cell.get_text(strip=True) for cell in cells)
                if any(header in row_text for header in ['Description', 'Type', 'Document']):
                    continue
                
                # Find document link
                doc_link = None
                doc_type = ""
                doc_description = ""
                
                for cell in cells:
                    link = cell.find('a')
                    if link and link.get('href'):
                        doc_link = link
                        break
                
                if not doc_link:
                    continue
                
                # Extract info based on table layout
                if len(cells) >= 5:  # 5-column layout
                    doc_type = cells[3].get_text(strip=True)
                    doc_description = cells[1].get_text(strip=True)
                elif len(cells) >= 3:  # 3-column layout
                    doc_type = cells[0].get_text(strip=True)
                    doc_description = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                
                href = doc_link.get('href', '')
                filename = doc_link.get_text(strip=True) or href.split('/')[-1]
                
                # Handle iXBRL
                if '/ix?doc=' in href:
                    actual_url = self._extract_url_from_ixbrl_link(href)
                    filename = actual_url.split('/')[-1] if '/' in actual_url else actual_url
                else:
                    actual_url = href
                
                # Score this document
                score = self._is_main_s1_document(filename, doc_type, doc_description)
                
                if score > 0:
                    # Check if we already have this candidate
                    existing = next((c for c in candidates if c['filename'] == filename), None)
                    if not existing:
                        candidates.append({
                            'filename': filename,
                            'url': actual_url,
                            'type': doc_type or 'S-1',
                            'description': doc_description or 'Registration Statement',
                            'score': score
                        })
                        logger.debug(f"S-1 table candidate: {filename} (score: {score})")
        
        # Sort candidates by score and return the best one
        if candidates:
            candidates.sort(key=lambda x: x['score'], reverse=True)
            best = candidates[0]
            logger.info(f"Selected S-1 document: {best['filename']} (score: {best['score']})")
            
            # Remove score from result
            del best['score']
            return best
        
        logger.warning("No suitable S-1 document found in index")
        return None
    
    def _parse_index_generic(self, soup: BeautifulSoup, filing_type: str) -> Optional[Dict]:
        """
        Generic index parser for non-S-1 filings (original logic)
        """
        # Priority 1: Look for iXBRL links
        ixbrl_links = soup.find_all('a', href=re.compile(r'/ix\?doc='))
        for link in ixbrl_links:
            href = link.get('href', '')
            link_text = link.get_text(strip=True)
            
            # Skip if it's clearly an exhibit or amendment
            if re.search(r'ex-?\d+|exhibit|amendment', link_text, re.IGNORECASE):
                continue
            
            actual_url = self._extract_url_from_ixbrl_link(href)
            filename = actual_url.split('/')[-1] if '/' in actual_url else actual_url
            
            # Check if filename has date pattern or ticker pattern
            has_date = re.search(r'\d{8}|\d{4}-\d{2}-\d{2}', filename)
            has_ticker = re.match(r'^[a-z]{1,5}[-_]', filename, re.IGNORECASE)
            
            if has_date or has_ticker:
                logger.info(f"Found iXBRL main document: {href} -> {actual_url}")
                return {
                    'filename': filename,
                    'url': actual_url,
                    'type': filing_type,
                    'description': 'Main Document (iXBRL)'
                }
        
        # Priority 2: Standard table parsing
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                
                if len(cells) < 3:
                    continue
                
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                
                # Skip header rows
                if any(header in ' '.join(cell_texts) for header in ['Description', 'Type', 'Document']):
                    continue
                
                # Handle different table layouts
                doc_link = None
                doc_type = None
                
                if len(cells) >= 5:  # 5-column layout
                    doc_cell = cells[2]  # Document column
                    type_text = cells[3].get_text(strip=True)  # Type column
                    doc_link = doc_cell.find('a')
                    doc_type = type_text
                elif len(cells) >= 3:  # 3-column layout
                    for i, cell in enumerate(cells):
                        link = cell.find('a')
                        if link and link.get('href'):
                            doc_link = link
                            doc_type = cells[0].get_text(strip=True)
                            break
                
                # Check if this is our target filing type
                if doc_link and doc_type:
                    if (filing_type.lower() in doc_type.lower() or 
                        filing_type.replace('-', '').lower() in doc_type.lower()):
                        
                        href = doc_link.get('href', '')
                        
                        if '/ix?doc=' in href:
                            actual_url = self._extract_url_from_ixbrl_link(href)
                            filename = actual_url.split('/')[-1]
                        else:
                            actual_url = href
                            filename = doc_link.get_text(strip=True) or href.split('/')[-1]
                        
                        return {
                            'filename': filename,
                            'url': actual_url,
                            'type': doc_type,
                            'description': 'Main Document'
                        }
        
        return None
    
    def _parse_important_exhibits(self, html_content: str) -> List[Dict]:
        """
        ENHANCED: 解析重要附件 - 支持 Exhibit 99 + 10.x 系列
        
        基于现有 _parse_exhibit_99_files 方法扩展，保持架构一致性
        优先级：Exhibit 99 > 10.1-10.9 > 10.10+
        
        Returns:
            List of exhibit file info dictionaries with priority scoring
        """
        exhibits = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 定义附件优先级和分类
        exhibit_patterns = {
            # 最高优先级：Exhibit 99（财务数据、新闻稿）
            'EX-99': {
                'priority': 100,
                'max_size_mb': 50,
                'patterns': [r'EX-99\.?\d*'],
                'description': 'Press Release/Financial Data'
            },
            # 高优先级：Exhibit 10.1-10.9（重大合同）
            'EX-10_CONTRACTS': {
                'priority': 90,
                'max_size_mb': 30,
                'patterns': [r'EX-10\.[1-9](?![0-9])'],  # 10.1 to 10.9 only
                'description': 'Material Contracts'
            },
            # 中等优先级：Exhibit 10.10+（高管补偿）
            'EX-10_COMPENSATION': {
                'priority': 80,
                'max_size_mb': 20,
                'patterns': [r'EX-10\.(?:[1-9]\d+|\d{2,})'],  # 10.10, 10.11, etc.
                'description': 'Executive Compensation'
            }
        }
        
        # 查找所有表格行
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                
                if len(cells) < 3:
                    continue
                
                # 获取行文本用于模式匹配
                row_text = ' '.join(cell.get_text(strip=True) for cell in cells)
                
                # 检查是否匹配任何重要附件模式
                for exhibit_type, config in exhibit_patterns.items():
                    for pattern in config['patterns']:
                        if re.search(pattern, row_text, re.IGNORECASE):
                            # 在该行中查找链接
                            for cell in cells:
                                link = cell.find('a')
                                if link and link.get('href'):
                                    href = link.get('href', '')
                                    
                                    # 跳过 iXBRL 查看器链接
                                    if '/ix?doc=' in href:
                                        continue
                                    
                                    filename = link.get_text(strip=True) or href.split('/')[-1]
                                    
                                    # 提取具体的附件编号
                                    exhibit_match = re.search(pattern, row_text, re.IGNORECASE)
                                    if exhibit_match:
                                        exhibit_num = exhibit_match.group(0)
                                        
                                        # 避免重复添加相同文件
                                        if not any(ex['filename'] == filename for ex in exhibits):
                                            exhibits.append({
                                                'filename': filename,
                                                'url': href,
                                                'type': exhibit_num,
                                                'category': exhibit_type,
                                                'description': f'{exhibit_num} - {config["description"]}',
                                                'priority': config['priority'],
                                                'max_size_mb': config['max_size_mb']
                                            })
                                            logger.debug(f"Found important exhibit: {exhibit_num} ({filename})")
                                    break
                            break  # 找到匹配的模式后，跳出模式循环
        
        # 按优先级排序，确保重要附件优先下载
        exhibits.sort(key=lambda x: x['priority'], reverse=True)
        
        # 限制附件数量避免过载
        if len(exhibits) > self.max_exhibits_per_filing:
            logger.warning(f"Found {len(exhibits)} exhibits, limiting to {self.max_exhibits_per_filing} highest priority")
            exhibits = exhibits[:self.max_exhibits_per_filing]
        
        logger.info(f"Identified {len(exhibits)} important exhibits for download")
        return exhibits
    
    def _parse_exhibit_99_files(self, html_content: str) -> List[Dict]:
        """
        保持向后兼容：原始 Exhibit 99 解析方法
        现在内部调用 _parse_important_exhibits 并过滤结果
        """
        all_exhibits = self._parse_important_exhibits(html_content)
        
        # 只返回 EX-99 系列，保持向后兼容
        exhibit_99_files = [
            exhibit for exhibit in all_exhibits 
            if exhibit['category'] == 'EX-99'
        ]
        
        logger.info(f"Found {len(exhibit_99_files)} Exhibit 99 file(s) (backward compatibility)")
        return exhibit_99_files
    
    def _validate_document_content(self, content: bytes, filing_type: str) -> bool:
        """
        Validate that downloaded content is a real document
        """
        # Size check
        size_kb = len(content) / 1024
        if size_kb < 10:
            logger.warning(f"Document suspiciously small: {size_kb:.1f}KB")
        
        # Content check
        try:
            text_sample = content[:5000].decode('utf-8', errors='ignore')
            
            # Check if it's an iXBRL viewer
            if self._is_ixbrl_viewer_page(text_sample):
                logger.warning("Downloaded content is an iXBRL viewer page")
                return False
            
            # For S-1, do additional validation
            if filing_type == FilingType.FORM_S1.value:
                # Check it's not just a fee table
                if 'CALCULATION OF FILING FEE' in text_sample and len(text_sample) < 2000:
                    logger.warning("Content appears to be only a fee calculation table")
                    return False
            
            # For files > 10KB, assume they're valid unless they're viewer pages
            if size_kb > 10:
                if 'loadViewer' not in text_sample and 'ixvFrame' not in text_sample:
                    return True
            
            # Check for filing-related markers
            filing_markers = [
                filing_type.upper().replace('-', ''),
                'FORM ' + filing_type.upper(),
                'REGISTRATION STATEMENT',
                'PROSPECTUS',
                'UNITED STATES',
                'SECURITIES',
                'pursuant to'
            ]
            
            for marker in filing_markers:
                if marker in text_sample.upper():
                    logger.debug(f"Found filing marker: {marker}")
                    return True
            
            # Check for financial content
            financial_markers = ['financial', 'consolidated', 'revenue', 'income']
            for marker in financial_markers:
                if marker in text_sample.lower():
                    logger.debug(f"Found financial marker: {marker}")
                    return True
            
            logger.warning(f"No valid markers found in document")
            return False
            
        except Exception as e:
            logger.error(f"Error validating content: {e}")
            return size_kb > 20
    
    def _validate_exhibit_size(self, exhibit: Dict, content: bytes) -> bool:
        """
        验证附件文件大小是否在合理范围内
        
        Args:
            exhibit: 附件信息字典
            content: 文件内容
            
        Returns:
            bool: 是否通过大小验证
        """
        size_mb = len(content) / (1024 * 1024)
        max_size_mb = exhibit.get('max_size_mb', 50)
        
        if size_mb > max_size_mb:
            logger.warning(f"Exhibit {exhibit['filename']} too large: {size_mb:.1f}MB > {max_size_mb}MB limit")
            return False
        
        if size_mb < 0.01:  # 10KB minimum
            logger.warning(f"Exhibit {exhibit['filename']} too small: {size_mb:.1f}MB")
            return False
        
        return True
    
    async def _try_alternative_patterns(self, client: httpx.AsyncClient, filing: Filing) -> Optional[Dict]:
        """
        Try common filename patterns when index parsing fails
        Based on successful patterns from database
        """
        date_str = filing.filing_date.strftime('%Y%m%d')
        ticker = filing.company.ticker.lower() if filing.company.ticker else ""
        form_type = filing.filing_type.value.lower().replace('-', '')
        
        # Patterns based on successful database examples
        patterns = []
        
        if filing.filing_type == FilingType.FORM_S1:
            # S-1 specific patterns from database
            patterns = [
                'forms-1.htm',  # Most common successful pattern
                f'{ticker}-s1.htm' if ticker else None,
                f'ea*-s1_{ticker}.htm' if ticker else None,
                f'd*s1.htm',
                f'tm*s1.htm',
                's-1.htm',
                's1.htm',
                'form-s1.htm',
            ]
        else:
            # Generic patterns for other filings
            patterns = [
                f"{filing.filing_type.value.lower()}.htm",
                f"form{form_type}.htm",
                f"{form_type}.htm",
                f"{ticker}-{date_str}.htm" if ticker else None,
                f"{ticker}_{date_str}.htm" if ticker else None,
            ]
        
        # Remove None values
        patterns = list(filter(None, patterns))
        
        acc_no = filing.accession_number
        cik = filing.company.cik.lstrip('0')
        base_url = f"{self.base_url}/{cik}/{acc_no}"
        
        for pattern in patterns:
            try:
                # For patterns with wildcards, skip (can't test directly)
                if '*' in pattern:
                    continue
                    
                test_url = f"{base_url}/{pattern}"
                logger.debug(f"Trying pattern: {test_url}")
                
                await self._rate_limit()
                response = await client.head(test_url, headers=self.headers, timeout=5.0)
                
                if response.status_code == 200:
                    logger.info(f"Found document using pattern: {pattern}")
                    return {
                        'filename': pattern,
                        'url': pattern,
                        'type': filing.filing_type.value,
                        'description': 'Main Document (pattern match)'
                    }
            except:
                continue
        
        return None
    
    async def download_filing(self, db: Session, filing: Filing) -> bool:
        """
        ENHANCED: 主下载方法，支持完整附件处理
        
        改进内容：
        1. 保持原有下载流程不变
        2. 为8-K添加完整附件处理（99 + 10.x系列）
        3. 智能优先级和容错机制
        4. 性能优化和大小限制
        """
        try:
            # Update status
            filing.status = ProcessingStatus.DOWNLOADING
            filing.processing_started_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Starting enhanced download for {filing.company.ticker} {filing.filing_type.value} "
                       f"({filing.accession_number})")
            
            # Create directory
            filing_dir = self._get_filing_directory(filing)
            filing_dir.mkdir(parents=True, exist_ok=True)
            
            async with httpx.AsyncClient(headers=self.headers, timeout=30.0) as client:
                # ========================= Phase 1: 下载索引页面 =========================
                urls_to_try = []
                
                # Most common format
                cik_no_zeros = filing.company.cik.lstrip('0')
                urls_to_try.append(f"{self.base_url}/{cik_no_zeros}/{filing.accession_number}/-index.htm")
                
                # With padded CIK
                cik_padded = filing.company.cik.zfill(10)
                urls_to_try.append(f"{self.base_url}/{cik_padded}/{filing.accession_number}/-index.htm")
                
                # Without dashes in accession
                acc_no_clean = filing.accession_number.replace("-", "")
                urls_to_try.append(f"{self.base_url}/{cik_no_zeros}/{acc_no_clean}/-index.htm")
                
                index_content = None
                successful_url = None
                
                for url in urls_to_try:
                    try:
                        logger.debug(f"Trying index URL: {url}")
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
                
                # Save index.htm
                index_path = filing_dir / "index.htm"
                with open(index_path, 'wb') as f:
                    f.write(index_content)
                
                # ========================= Phase 2: 下载主文档 =========================
                index_text = index_content.decode('utf-8', errors='ignore')
                main_doc = self._parse_index_enhanced(index_text, filing.filing_type.value)
                
                if not main_doc:
                    logger.warning("Could not find main document in index, trying alternative patterns")
                    main_doc = await self._try_alternative_patterns(client, filing)
                
                if main_doc:
                    # Download the main document
                    doc_url = main_doc['url']
                    
                    # Handle relative URLs
                    if not doc_url.startswith('http'):
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
                        if self._validate_document_content(doc_content, filing.filing_type.value):
                            # Save the document
                            filename = main_doc['filename']
                            if not filename.endswith(('.htm', '.html', '.txt')):
                                filename = f"{filing.filing_type.value.lower()}.htm"
                            
                            doc_path = filing_dir / filename
                            with open(doc_path, 'wb') as f:
                                f.write(doc_content)
                            
                            logger.info(f"✅ Successfully downloaded {filename} "
                                       f"({len(doc_content)/1024:.1f}KB)")
                            
                            # Set both URL fields for compatibility
                            filing.primary_doc_url = doc_url
                            filing.primary_document_url = doc_url
                            
                            # Commit the URL updates
                            db.commit()
                        else:
                            logger.error("Downloaded content failed validation")
                            # For S-1, try harder to find the right document
                            if filing.filing_type == FilingType.FORM_S1:
                                logger.info("Attempting alternative S-1 document search")
                                main_doc = await self._try_alternative_patterns(client, filing)
                                if main_doc:
                                    # Retry download with new document
                                    # (recursive call limited to once)
                                    pass
                            raise Exception("Invalid document content")
                    else:
                        raise Exception(f"Failed to download document: HTTP {doc_response.status_code}")
                else:
                    logger.warning("Could not find main document in any format")
                    # Don't fail completely - we still have the index
                
                # ========================= Phase 3: 下载重要附件 =========================
                if filing.filing_type == FilingType.FORM_8K:
                    logger.info("This is an 8-K filing, checking for important exhibits...")
                    
                    # 使用增强的附件解析方法
                    important_exhibits = self._parse_important_exhibits(index_text)
                    
                    if important_exhibits:
                        logger.info(f"Found {len(important_exhibits)} important exhibit(s) to download:")
                        
                        # 显示发现的附件信息
                        for exhibit in important_exhibits:
                            logger.info(f"  - {exhibit['type']}: {exhibit['filename']} "
                                       f"(Priority: {exhibit['priority']}, Max: {exhibit['max_size_mb']}MB)")
                        
                        successful_downloads = 0
                        failed_downloads = 0
                        
                        for exhibit in important_exhibits:
                            try:
                                exhibit_url = exhibit['url']
                                if not exhibit_url.startswith('http'):
                                    if exhibit_url.startswith('/'):
                                        exhibit_url = f"https://www.sec.gov{exhibit_url}"
                                    else:
                                        base_url_parts = successful_url.rsplit('/', 1)[0]
                                        exhibit_url = f"{base_url_parts}/{exhibit_url}"
                                
                                logger.info(f"Downloading {exhibit['type']} ({exhibit['category']}): {exhibit['filename']}")
                                
                                await self._rate_limit()
                                exhibit_response = await client.get(exhibit_url, timeout=60.0)
                                
                                if exhibit_response.status_code == 200:
                                    exhibit_content = exhibit_response.content
                                    
                                    # 验证文件大小
                                    if self._validate_exhibit_size(exhibit, exhibit_content):
                                        exhibit_path = filing_dir / exhibit['filename']
                                        with open(exhibit_path, 'wb') as f:
                                            f.write(exhibit_content)
                                        
                                        size_mb = len(exhibit_content) / (1024 * 1024)
                                        logger.info(f"✅ Successfully downloaded {exhibit['filename']} "
                                                   f"({size_mb:.1f}MB)")
                                        successful_downloads += 1
                                    else:
                                        logger.warning(f"❌ Skipped {exhibit['filename']} - size validation failed")
                                        failed_downloads += 1
                                else:
                                    logger.warning(f"❌ Failed to download {exhibit['filename']}: "
                                                  f"HTTP {exhibit_response.status_code}")
                                    failed_downloads += 1
                                    
                            except Exception as e:
                                logger.error(f"❌ Error downloading exhibit {exhibit['filename']}: {e}")
                                failed_downloads += 1
                                # 单个附件失败不影响整体处理，继续下载其他附件
                                continue
                        
                        logger.info(f"📊 Exhibit download summary: "
                                   f"{successful_downloads} successful, {failed_downloads} failed")
                        
                        # 如果有附件成功下载，记录到日志
                        if successful_downloads > 0:
                            logger.info(f"🎉 Enhanced 8-K processing completed with {successful_downloads} exhibits")
                
                # Update status to PARSING
                filing.status = ProcessingStatus.PARSING
                db.commit()
                
                # ========================= Phase 4: 发送推送通知 =========================
                try:
                    logger.info(f"Phase 4: Triggering push notification for filing {filing.id}")
                    
                    # 调用通知服务发送通知
                    notification_count = notification_service.send_filing_notification(
                        db=db,
                        filing=filing,
                        notification_type="filing_release"
                    )
                    
                    if notification_count > 0:
                        logger.info(f"✅ Successfully sent {notification_count} push notifications")
                    else:
                        logger.info("No users subscribed to notifications for this filing")
                        
                except Exception as notification_error:
                    # 通知失败不应该影响下载流程
                    logger.error(f"Failed to send push notifications: {notification_error}")
                    # 继续执行，不中断下载流程
                # =========================================================================
                
                logger.info(f"🎯 Successfully completed enhanced download for {filing.accession_number}")
                return True
                    
        except Exception as e:
            logger.error(f"Error downloading filing {filing.accession_number}: {e}")
            
            # Update status to failed
            filing.status = ProcessingStatus.FAILED
            filing.error_message = str(e)
            db.commit()
            
            return False
    
    def get_filing_path(self, filing: Filing) -> Optional[Path]:
        """Get the path to the downloaded filing document"""
        filing_dir = self._get_filing_directory(filing)
        
        if not filing_dir.exists():
            return None
        
        # For S-1, prioritize certain filenames
        if filing.filing_type == FilingType.FORM_S1:
            priority_patterns = [
                'forms-1.htm',
                '*-s1*.htm',
                '*s1.htm',
                's-1.htm',
                's1.htm'
            ]
            
            for pattern in priority_patterns:
                files = list(filing_dir.glob(pattern))
                # Exclude fee tables
                files = [f for f in files if not self._is_fee_calculation_table(f.name)]
                if files:
                    return files[0]
        
        # Generic search for main document
        for pattern in ['*.htm', '*.html', '*.txt']:
            files = list(filing_dir.glob(pattern))
            # Exclude index and exhibits
            files = [f for f in files if f.name != 'index.htm' and not re.search(r'ex-?\d+|kex\d+', f.name, re.I)]
            if files:
                # Return the largest file
                return max(files, key=lambda f: f.stat().st_size)
        
        # Fallback to index.htm
        index_path = filing_dir / 'index.htm'
        if index_path.exists():
            return index_path
        
        return None


# Create singleton instance
filing_downloader = FilingDownloader()
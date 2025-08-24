# app/services/text_extractor.py
"""
Text Extractor Service - Enhanced Version with Complete Exhibit Processing

ENHANCED: 支持 Exhibit 99 + 10.x 系列的完整附件提取
- 扩展现有 _extract_exhibit_99 方法为 _extract_important_exhibits
- 保持向后兼容，所有现有功能和调用方式不变
- 智能优先级处理：99系列 > 10.1-10.9 > 10.10+
- 性能优化：Token预算分配、内容整合优化

核心改进：
1. 统一附件提取架构
2. 智能内容整合和优先级排序
3. 附件类型标识和来源追踪
4. 向后兼容性保证
5. 保持表格结构完整的革命性方法
"""
import re
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


class TextExtractor:
    """
    Extract structured text from SEC filing HTML documents
    Enhanced with comprehensive exhibit processing for investment-grade analysis
    """
    
    def __init__(self):
        self.min_section_length = 100  # Minimum characters for a valid section
        self.max_section_length = 50000  # Maximum characters to avoid memory issues
        
        # ENHANCED: 附件处理配置
        self.exhibit_config = {
            'EX-99': {
                'priority': 100,
                'max_chars': 100000,
                'patterns': [
                    "*ex99*.htm", "*ex99*.html",
                    "*kex99*.htm", "*kex99*.html", 
                    "*dex99*.htm", "*dex99*.html",
                    "ex-99*.htm", "ex-99*.html",
                    "exhibit99*.htm", "exhibit99*.html"
                ],
                'description': 'Press Release/Financial Data'
            },
            'EX-10_CONTRACTS': {
                'priority': 90,
                'max_chars': 80000,
                'patterns': [
                    "*ex10[._-][1-9].htm", "*ex10[._-][1-9].html",
                    "*kex10[._-][1-9].htm", "*dex10[._-][1-9].htm",
                    "ex-10.[1-9]*.htm", "ex-10.[1-9]*.html"
                ],
                'description': 'Material Contracts'
            },
            'EX-10_COMPENSATION': {
                'priority': 80,
                'max_chars': 60000,
                'patterns': [
                    "*ex10[._-]1[0-9].htm", "*ex10[._-]1[0-9].html",
                    "*ex10[._-][2-9][0-9].htm", "*ex10[._-][2-9][0-9].html",
                    "*kex10[._-]1[0-9].htm", "*dex10[._-]1[0-9].htm",
                    "ex-10.1[0-9]*.htm", "ex-10.2[0-9]*.htm"
                ],
                'description': 'Executive Compensation'
            }
        }
        
        # Define filing type patterns with priority
        self.filing_patterns = {
            '8-K': [
                (r'FORM\s*8[\s\-]*K', 100),
                (r'CURRENT\s+REPORT', 90),
                (r'Pursuant\s+to\s+Section\s+13\s+or\s+15\(d\)', 80),
                (r'Item\s+\d+\.\d+', 70),
            ],
            '10-K': [
                (r'FORM\s*10[\s\-]*K', 100),
                (r'ANNUAL\s+REPORT', 90),
                (r'Pursuant\s+to\s+Section\s+13\s+or\s+15\(d\).*annual', 80),
                (r'Item\s+1[.\s]+Business', 70),
                (r'Item\s+7[.\s]+Management', 70),
            ],
            '10-Q': [
                (r'FORM\s*10[\s\-]*Q', 100),
                (r'QUARTERLY\s+REPORT', 90),
                (r'Pursuant\s+to\s+Section\s+13\s+or\s+15\(d\).*quarterly', 80),
                (r'For\s+the\s+(?:quarterly\s+period|three\s+months)', 70),
            ],
            'S-1': [
                (r'FORM\s*S[\s\-]*1', 100),
                (r'REGISTRATION\s+STATEMENT', 90),
                (r'PROSPECTUS', 80),
                (r'Under\s+the\s+Securities\s+Act\s+of\s+1933', 70),
                (r'IPO\s+REGISTRATION', 60),
                (r'INITIAL\s+PUBLIC\s+OFFERING', 60),
            ]
        }
        
        # Key sections for each filing type
        self.key_sections = {
            '10-K': {
                'Item 1': {'pattern': r'Item\s*1[.\s]+Business', 'max_chars': 30000},
                'Item 1A': {'pattern': r'Item\s*1A[.\s]+Risk\s+Factors', 'max_chars': 30000},
                'Item 7': {'pattern': r'Item\s*7[.\s]+Management.{0,50}Discussion', 'max_chars': 40000},
                'Item 8': {'pattern': r'Item\s*8[.\s]+Financial\s+Statements', 'max_chars': 50000},
            },
            '10-Q': {
                'Financial Statements': {'pattern': r'(?:Condensed\s+)?(?:Consolidated\s+)?Financial\s+Statements', 'max_chars': 40000},
                'MD&A': {'pattern': r'Management.{0,50}Discussion\s+and\s+Analysis', 'max_chars': 35000},
            },
            '8-K': {
                'Items': {'pattern': r'Item\s+\d+\.\d+', 'max_chars': 10000},
            },
            'S-1': {
                'Prospectus Summary': {'pattern': r'(?:PROSPECTUS\s+)?SUMMARY', 'max_chars': 20000},
                'Risk Factors': {'pattern': r'RISK\s+FACTORS', 'max_chars': 30000},
                'Business': {'pattern': r'(?:OUR\s+)?BUSINESS|BUSINESS\s+OVERVIEW', 'max_chars': 25000},
                'Use of Proceeds': {'pattern': r'USE\s+OF\s+PROCEEDS', 'max_chars': 10000},
                'Management': {'pattern': r'MANAGEMENT|DIRECTORS\s+AND\s+EXECUTIVE', 'max_chars': 15000},
                'Financial Statements': {'pattern': r'FINANCIAL\s+STATEMENTS', 'max_chars': 40000},
            }
        }
        
        # S-1 critical sections based on actual TOC structure
        self.s1_critical_sections = {
            'PROSPECTUS SUMMARY': {
                'patterns': [r'PROSPECTUS\s+SUMMARY', r'SUMMARY\s+OF\s+THE\s+OFFERING', r'INVESTMENT\s+HIGHLIGHTS'],
                'keywords': ['overview', 'investment', 'highlights', 'summary', 'opportunity'],
                'priority': 100
            },
            'RISK FACTORS': {
                'patterns': [r'RISK\s+FACTORS', r'INVESTMENT\s+RISKS'],
                'keywords': ['risks', 'uncertainties', 'challenges', 'risk factors', 'may adversely affect'],
                'priority': 95
            },
            'USE OF PROCEEDS': {
                'patterns': [r'USE\s+OF\s+PROCEEDS', r'PROCEEDS\s+FROM\s+THE\s+OFFERING'],
                'keywords': ['proceeds', 'allocation', 'purposes', 'use of proceeds', 'intend to use'],
                'priority': 90
            },
            'BUSINESS': {
                'patterns': [r'BUSINESS(?:\s+OVERVIEW)?', r'OUR\s+BUSINESS', r'COMPANY\s+OVERVIEW'],
                'keywords': ['business model', 'revenue', 'operations', 'products', 'services', 'competitive'],
                'priority': 85
            },
            'MANAGEMENT\'S DISCUSSION AND ANALYSIS': {
                'patterns': [r'MANAGEMENT.{0,5}S?\s+DISCUSSION\s+AND\s+ANALYSIS', r'MD&A'],
                'keywords': ['financial condition', 'results of operations', 'liquidity', 'capital resources'],
                'priority': 80
            },
            'FINANCIAL STATEMENTS': {
                'patterns': [r'FINANCIAL\s+STATEMENTS', r'CONSOLIDATED\s+FINANCIAL\s+STATEMENTS'],
                'keywords': ['balance sheet', 'income statement', 'cash flow', 'statement of operations'],
                'priority': 75
            },
            'MANAGEMENT': {
                'patterns': [r'MANAGEMENT(?:\s+TEAM)?', r'DIRECTORS\s+AND\s+EXECUTIVE\s+OFFICERS', r'OUR\s+TEAM'],
                'keywords': ['executive', 'directors', 'management team', 'leadership', 'officers'],
                'priority': 70
            },
            'PRINCIPAL STOCKHOLDERS': {
                'patterns': [r'PRINCIPAL\s+(?:AND\s+SELLING\s+)?STOCKHOLDERS', r'OWNERSHIP', r'SECURITY\s+OWNERSHIP'],
                'keywords': ['ownership', 'shareholders', 'equity holders', 'beneficial ownership'],
                'priority': 60
            },
            'DESCRIPTION OF CAPITAL STOCK': {
                'patterns': [r'DESCRIPTION\s+OF\s+(?:CAPITAL\s+)?STOCK', r'CAPITALIZATION'],
                'keywords': ['common stock', 'preferred stock', 'shares', 'capital structure'],
                'priority': 55
            },
            'UNDERWRITING': {
                'patterns': [r'UNDERWRITING', r'PLAN\s+OF\s+DISTRIBUTION'],
                'keywords': ['underwriters', 'offering price', 'commission', 'distribution'],
                'priority': 50
            }
        }
    
    def extract_from_filing(self, filing_dir: Path) -> Dict[str, str]:
        """
        Extract text from all documents in a filing directory
        
        ENHANCED: 现在支持完整的附件处理（99 + 10.x系列）
        """
        # Check if directory exists
        if not filing_dir.exists():
            logger.warning(f"Filing directory does not exist: {filing_dir}")
            return {
                'error': 'Filing directory not found',
                'full_text': '',
                'primary_content': '',
                'enhanced_text': '',
                'filing_type': 'UNKNOWN'
            }
        
        # First, check if we have a TXT file (preferred)
        txt_files = list(filing_dir.glob("*.txt"))
        if txt_files:
            txt_file = txt_files[0]
            logger.info(f"Found TXT file, using {txt_file.name}")
            return self.extract_from_txt(txt_file)
        
        # For S-1, prioritize correct document patterns
        html_files = []
        if filing_dir.exists():
            # Check for S-1 specific patterns first
            s1_patterns = ['forms-1.htm', '*-s1*.htm', '*s1.htm', 's-1.htm', 's1.htm']
            for pattern in s1_patterns:
                matching_files = list(filing_dir.glob(pattern))
                # Exclude fee tables
                matching_files = [f for f in matching_files if not self._is_fee_table(f.name)]
                if matching_files:
                    html_files = matching_files
                    break
        
        # If no S-1 specific files, find general HTML documents
        if not html_files:
            html_files = [f for f in filing_dir.glob("*.htm") if f.name != "index.htm"]
            html_files.extend([f for f in filing_dir.glob("*.html") if f.name != "index.html"])
            # Exclude fee tables
            html_files = [f for f in html_files if not self._is_fee_table(f.name)]
        
        if not html_files:
            logger.warning(f"No filing documents found in {filing_dir}")
            return {
                'error': 'No filing documents found',
                'full_text': '',
                'primary_content': '',
                'enhanced_text': '',
                'filing_type': 'UNKNOWN'
            }
        
        # Use the first non-fee HTML file
        main_doc = html_files[0]
        logger.info(f"Extracting text from {main_doc.name}")
        
        # Extract from main document
        sections = self.extract_from_html(main_doc)
        
        # ENHANCED: 提取重要附件内容（99 + 10.x系列）
        if sections.get('filing_type') == '8-K':
            important_exhibits_content = self._extract_important_exhibits(filing_dir)
            if important_exhibits_content:
                # 获取附件统计信息
                exhibit_stats = important_exhibits_content.get('stats', {})
                total_exhibits = exhibit_stats.get('total_found', 0)
                successful_extracts = exhibit_stats.get('successful_extracts', 0)
                
                logger.info(f"🎯 Enhanced 8-K processing: {successful_extracts}/{total_exhibits} exhibits extracted")
                
                # 整合附件内容到主要部分
                exhibit_content = important_exhibits_content.get('content', '')
                if exhibit_content:
                    # 添加到 primary_content
                    if 'primary_content' in sections:
                        sections['primary_content'] += f"\n\n{'='*60}\nIMPORTANT EXHIBITS CONTENT\n{'='*60}\n\n{exhibit_content}"
                    else:
                        sections['primary_content'] = exhibit_content
                    
                    # 添加到其他部分以保持兼容性
                    if 'full_text' in sections:
                        sections['full_text'] += f"\n\n{exhibit_content}"
                    
                    if 'enhanced_text' in sections:
                        sections['enhanced_text'] += f"\n\n## IMPORTANT EXHIBITS CONTENT\n\n{exhibit_content}"
                    
                    # 保持向后兼容：仍然提供单独的exhibit_99_content
                    exhibit_99_only = important_exhibits_content.get('exhibit_99_content', '')
                    if exhibit_99_only:
                        sections['exhibit_99_content'] = exhibit_99_only
                    
                    # 新增：提供完整的附件内容分类
                    sections['important_exhibits_content'] = exhibit_content
                    sections['exhibit_processing_stats'] = exhibit_stats
        
        return sections
    
    def _is_fee_table(self, filename: str) -> bool:
        """Check if a file is a fee calculation table"""
        filename_lower = filename.lower()
        fee_indicators = [
            'ex-fee', 'exfee', 'ex_fee',
            'ex-filingfees', 'exfilingfees',
            'filing-fees', 'filingfees',
            'fee-table', 'feetable',
            'ex107', 'ex_107', 'ex-107',
            'calculation'
        ]
        
        for indicator in fee_indicators:
            if indicator in filename_lower:
                return True
        
        # Check if it's an exhibit (except S-1 main docs)
        if re.match(r'^ex[_-]?\d+', filename_lower) and 's1' not in filename_lower:
            return True
        
        return False
    
    def _extract_important_exhibits(self, filing_dir: Path) -> Optional[Dict]:
        """
        ENHANCED: 提取重要附件内容 - 支持 99 + 10.x 系列
        
        基于现有 _extract_exhibit_99 方法扩展，保持架构一致性
        
        Returns:
            Dict containing:
            - content: 整合的附件内容
            - exhibit_99_content: 仅99系列内容（向后兼容）
            - stats: 处理统计信息
        """
        exhibit_contents = []
        exhibit_99_only = []  # 向后兼容
        processing_stats = {
            'total_found': 0,
            'successful_extracts': 0,
            'by_category': {}
        }
        
        # 按优先级处理各类附件
        for category, config in self.exhibit_config.items():
            category_files = []
            category_content = []
            
            # 查找该类别的附件文件
            for pattern in config['patterns']:
                found_files = list(filing_dir.glob(pattern))
                category_files.extend(found_files)
            
            # 去重并排序
            category_files = sorted(set(category_files), key=lambda x: x.name)
            
            if not category_files:
                logger.debug(f"No {category} files found")
                processing_stats['by_category'][category] = {'found': 0, 'extracted': 0}
                continue
            
            logger.info(f"Found {len(category_files)} {category} file(s): {[f.name for f in category_files]}")
            processing_stats['by_category'][category] = {'found': len(category_files), 'extracted': 0}
            processing_stats['total_found'] += len(category_files)
            
            # 提取每个文件的内容
            for exhibit_file in category_files:
                try:
                    # 检查文件大小
                    file_size_mb = exhibit_file.stat().st_size / (1024 * 1024)
                    max_size_mb = config.get('max_size_mb', 50)
                    
                    if file_size_mb > max_size_mb:
                        logger.warning(f"Skipping {exhibit_file.name} - file too large ({file_size_mb:.1f}MB > {max_size_mb}MB)")
                        continue
                    
                    # 读取并提取内容
                    with open(exhibit_file, 'r', encoding='utf-8', errors='ignore') as f:
                        html_content = f.read()
                    
                    # 使用BeautifulSoup解析
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # 提取增强内容 - 使用表格结构保持方法
                    enhanced_content = self._extract_enhanced_content_from_soup(soup)
                    
                    if enhanced_content and len(enhanced_content) > 100:
                        # 为该附件添加标题头
                        exhibit_header = f"\n{'='*50}\n{config['description']}: {exhibit_file.name}\n{'-'*30}\nCategory: {category}\nPriority: {config['priority']}\n{'='*50}\n"
                        
                        # 限制内容长度
                        max_chars = config.get('max_chars', 60000)
                        if len(enhanced_content) > max_chars:
                            logger.warning(f"Truncating {exhibit_file.name} content from {len(enhanced_content)} to {max_chars} chars")
                            enhanced_content = enhanced_content[:max_chars] + "\n\n[Content truncated due to length...]"
                        
                        # 添加到相应的内容集合
                        full_exhibit_content = exhibit_header + enhanced_content
                        category_content.append(full_exhibit_content)
                        
                        # 向后兼容：如果是EX-99，也添加到exhibit_99_only
                        if category == 'EX-99':
                            ex99_header = f"\n{'='*40}\nExhibit 99: {exhibit_file.name}\n{'='*40}\n"
                            exhibit_99_only.append(ex99_header + enhanced_content)
                        
                        processing_stats['by_category'][category]['extracted'] += 1
                        processing_stats['successful_extracts'] += 1
                        
                        logger.info(f"✅ Extracted {category} content from {exhibit_file.name}: {len(enhanced_content)} chars")
                
                except Exception as e:
                    logger.error(f"❌ Error extracting from {exhibit_file.name}: {e}")
                    continue
            
            # 将该类别的内容添加到总体内容中
            if category_content:
                # 添加类别分隔符
                category_separator = f"\n\n{'🔸'*20} {config['description'].upper()} {'🔸'*20}\n"
                exhibit_contents.append(category_separator + '\n\n'.join(category_content))
        
        # 整合所有内容
        result = {}
        
        if exhibit_contents:
            # 主要内容：所有重要附件
            combined_content = '\n\n'.join(exhibit_contents)
            
            # 应用总体大小限制
            max_total_chars = 300000  # 总体限制
            if len(combined_content) > max_total_chars:
                logger.warning(f"Total exhibit content truncated from {len(combined_content)} to {max_total_chars} chars")
                combined_content = combined_content[:max_total_chars] + "\n\n[Total exhibit content truncated...]"
            
            result['content'] = combined_content
            result['stats'] = processing_stats
            
            # 向后兼容：单独的exhibit_99内容
            if exhibit_99_only:
                exhibit_99_combined = '\n\n'.join(exhibit_99_only)
                if len(exhibit_99_combined) > 100000:
                    exhibit_99_combined = exhibit_99_combined[:100000] + "\n\n[Exhibit 99 content truncated...]"
                result['exhibit_99_content'] = exhibit_99_combined
            
            logger.info(f"🎉 Successfully processed important exhibits: "
                       f"{processing_stats['successful_extracts']}/{processing_stats['total_found']} files")
            
            return result
        
        logger.info("No important exhibits found")
        return None
    
    def _extract_exhibit_99(self, filing_dir: Path) -> Optional[str]:
        """
        向后兼容：保持原有 _extract_exhibit_99 方法签名和行为
        
        现在内部调用增强的 _extract_important_exhibits 方法，
        但只返回 Exhibit 99 内容以保持向后兼容
        """
        important_exhibits = self._extract_important_exhibits(filing_dir)
        
        if important_exhibits and 'exhibit_99_content' in important_exhibits:
            return important_exhibits['exhibit_99_content']
        
        return None
    
    def extract_from_txt(self, txt_path: Path) -> Dict[str, str]:
        """
        Extract text from SEC TXT filing
        """
        try:
            with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Handle empty file
            if not content:
                logger.warning(f"TXT file is empty: {txt_path}")
                return {
                    'full_text': '',
                    'primary_content': '',
                    'enhanced_text': '',
                    'filing_type': 'UNKNOWN'
                }
            
            # Remove SEC document headers
            header_end = content.find('</SEC-HEADER>')
            if header_end != -1:
                content = content[header_end + len('</SEC-HEADER>'):]
            
            # Find the main document section
            doc_start = content.find('<DOCUMENT>')
            doc_end = content.find('</DOCUMENT>')
            
            if doc_start != -1 and doc_end != -1:
                main_content = content[doc_start:doc_end]
            else:
                main_content = content
            
            # Remove HTML/XML tags
            main_content = re.sub(r'<[^>]+>', ' ', main_content)
            
            # Clean up the text
            main_content = self._clean_text(main_content)
            
            # Identify filing type with enhanced method
            filing_type = self._identify_filing_type_enhanced(main_content)
            logger.info(f"Document identified as: {filing_type}")
            
            # Extract sections based on filing type
            sections = self._extract_sections_by_type(main_content, filing_type)
            
            # Generate enhanced text (Markdown format)
            enhanced_text = self._generate_enhanced_markdown_from_text(main_content, filing_type)
            
            # Always include full text and primary content
            sections['full_text'] = main_content
            sections['enhanced_text'] = enhanced_text
            sections['filing_type'] = filing_type
            
            # Ensure we have quality primary content
            if 'primary_content' not in sections or len(sections.get('primary_content', '')) < 1000:
                sections['primary_content'] = self._extract_smart_content(main_content, filing_type)
            
            return sections
            
        except Exception as e:
            logger.error(f"Error extracting from TXT file {txt_path}: {e}")
            return {
                'error': str(e),
                'full_text': '',
                'primary_content': '',
                'enhanced_text': '',
                'filing_type': 'UNKNOWN'
            }
    
    def extract_from_html(self, html_path: Path) -> Dict[str, str]:
        """
        Extract structured text sections from an HTML filing with Markdown enhancement
        """
        try:
            with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            
            # Handle empty file
            if not html_content:
                logger.warning(f"HTML file is empty: {html_path}")
                return {
                    'full_text': '',
                    'primary_content': '',
                    'enhanced_text': '',
                    'filing_type': 'UNKNOWN'
                }
            
            # Check if this is just a fee calculation table (for S-1)
            if len(html_content) < 5000 and 'CALCULATION OF FILING FEE' in html_content:
                logger.warning(f"File appears to be only a fee calculation table: {html_path}")
                # Try to find the real S-1 document in the same directory
                parent_dir = html_path.parent
                alt_files = [f for f in parent_dir.glob("*.htm") if not self._is_fee_table(f.name) and f != html_path]
                if alt_files:
                    logger.info(f"Found alternative file: {alt_files[0].name}")
                    return self.extract_from_html(alt_files[0])
            
            # Identify filing type from raw HTML first
            filing_type = self._identify_filing_type_enhanced(html_content)
            logger.info(f"Initial document type identified from HTML: {filing_type}")
            
            # Check if this is an iXBRL document
            if 'ix:' in html_content or 'inline XBRL' in html_content.lower():
                logger.info("Detected iXBRL document, using special extraction")
                return self._extract_from_ixbrl(html_content, filing_type)
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # REVOLUTIONARY: Extract enhanced content with Markdown table conversion
            enhanced_text = self._extract_enhanced_content_from_soup(soup)
            
            # Remove script and style elements
            for element in soup(['script', 'style', 'link', 'meta']):
                element.decompose()
            
            # Extract text
            text = soup.get_text()
            
            # Clean up text
            text = self._clean_text(text)
            
            # If text is too short, try alternative extraction
            if len(text) < 500:
                logger.warning(f"Extracted text too short ({len(text)} chars), trying alternative methods")
                text = self._extract_all_text_content(soup)
            
            # Extract sections based on filing type
            sections = self._extract_sections_by_type(text, filing_type)
            
            # For S-1, also try intelligent extraction from HTML structure
            if filing_type == 'S-1':
                html_sections = self._extract_s1_from_html_structure(soup)
                if html_sections:
                    sections.update(html_sections)
            
            # Always ensure we have these keys
            sections['full_text'] = text
            sections['enhanced_text'] = enhanced_text  # NEW: Markdown enhanced text
            sections['filing_type'] = filing_type
            
            # Ensure quality primary content
            if 'primary_content' not in sections or len(sections.get('primary_content', '')) < 1000:
                sections['primary_content'] = self._extract_smart_content(text, filing_type)
            
            return sections
            
        except Exception as e:
            logger.error(f"Error extracting text from {html_path}: {e}")
            return {
                'error': str(e),
                'full_text': '',
                'primary_content': '',
                'enhanced_text': '',
                'filing_type': 'UNKNOWN'
            }
    
    def _categorize_exhibit_file(self, filename: str) -> Optional[str]:
        """
        根据文件名判断附件类别
        
        Returns:
            附件类别标识符或None
        """
        filename_lower = filename.lower()
        
        # 检查各类附件模式
        for category, config in self.exhibit_config.items():
            for pattern in config['patterns']:
                # 将glob模式转换为正则表达式
                regex_pattern = pattern.replace('*', '.*').replace('.', r'\.')
                if re.match(regex_pattern, filename_lower):
                    return category
        
        return None
    
    def _extract_enhanced_content_from_soup(self, soup: BeautifulSoup) -> str:
        """
        REVOLUTIONARY: Extract content with Markdown table conversion for accurate financial data
        
        This method addresses the core problem identified in the solution document:
        - Converts HTML tables to clean Markdown format
        - Preserves table structure instead of creating chaotic separators
        - Enhances key financial data with proper markup
        """
        logger.info("Starting enhanced content extraction with Markdown table conversion")
        
        # Build Markdown document
        markdown_doc = []
        
        # 1. Process tables - convert to clean Markdown tables
        tables_processed = 0
        for table in soup.find_all('table'):
            if self._is_financial_table(table):
                markdown_table = self._table_to_markdown_clean(table)
                if markdown_table:
                    markdown_doc.append(markdown_table)
                    tables_processed += 1
                    
        logger.info(f"Processed {tables_processed} financial tables into Markdown format")
        
        # 2. Process text sections - enhance with markup
        for section in self._find_sections(soup):
            enhanced_section = self._enhance_text_section(section)
            if enhanced_section:
                markdown_doc.append(enhanced_section)
        
        # 3. Combine all content
        enhanced_text = '\n\n'.join(markdown_doc)
        
        # 4. Final cleanup and validation
        enhanced_text = self._clean_text(enhanced_text)
        
        logger.info(f"Generated enhanced Markdown document: {len(enhanced_text)} chars")
        return enhanced_text
    
    def _is_financial_table(self, table_soup) -> bool:
        """
        Determine if a table contains financial data
        """
        table_text = table_soup.get_text().lower()
        
        # Financial keywords that indicate important tables
        financial_keywords = [
            'revenue', 'income', 'assets', 'liabilities', 'cash', 'earnings',
            'net sales', 'gross profit', 'operating', 'total', 'shares',
            'million', 'billion', 'thousand', '$', 'consolidated',
            'balance sheet', 'statement', 'fiscal', 'quarter', 'year'
        ]
        
        # Count keyword matches
        keyword_matches = sum(1 for keyword in financial_keywords if keyword in table_text)
        
        # Check for financial numbers
        has_financial_numbers = bool(re.search(r'\$[\d,]+|\d+[,.]?\d*\s*(?:million|billion)', table_text))
        
        # Table must have multiple rows and columns
        rows = len(table_soup.find_all('tr'))
        
        return keyword_matches >= 2 and has_financial_numbers and rows >= 2
    
    def _table_to_markdown_clean(self, table_soup) -> str:
        """
        CORE FIX: Convert HTML table to clean Markdown format
        
        This addresses the main problem: BeautifulSoup's get_text() creates chaotic
        separators that confuse AI. Instead, we preserve table structure in Markdown.
        
        Before: | | | | | | | | 13,640 | | | 15,009 | |
        After:  | Net sales | 3,535 | 5,082 | 13,640 | 15,009 |
        """
        try:
            markdown_lines = []
            
            rows = table_soup.find_all('tr')
            if not rows:
                return ""
            
            # Process each row
            for row_idx, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                
                # Extract cell contents and filter empty cells
                clean_cells = []
                for cell in cells:
                    cell_text = cell.get_text().strip()
                    # Only include cells with meaningful content
                    if cell_text and len(cell_text) > 0:
                        # Clean up the text
                        cell_text = re.sub(r'\s+', ' ', cell_text)
                        clean_cells.append(cell_text)
                
                # Only include rows with substantial content
                if clean_cells and len(clean_cells) >= 2:
                    # Create Markdown table row
                    markdown_row = "| " + " | ".join(clean_cells) + " |"
                    markdown_lines.append(markdown_row)
                    
                    # Add header separator after first row (if it looks like a header)
                    if row_idx == 0 and len(markdown_lines) == 1:
                        # Create separator row
                        separator_cells = ["---"] * len(clean_cells)
                        separator_row = "| " + " | ".join(separator_cells) + " |"
                        markdown_lines.append(separator_row)
            
            # Return the Markdown table
            if len(markdown_lines) >= 3:  # Header + separator + at least one data row
                result = '\n'.join(markdown_lines)
                logger.debug(f"Created Markdown table with {len(markdown_lines)} rows")
                return result
            else:
                return ""
                
        except Exception as e:
            logger.error(f"Error converting table to Markdown: {e}")
            return ""
    
    def _find_sections(self, soup: BeautifulSoup) -> List:
        """
        Find meaningful text sections for enhancement
        """
        sections = []
        
        # Find paragraphs and div elements with substantial text
        for element in soup.find_all(['p', 'div']):
            text = element.get_text().strip()
            if len(text) > 200:  # Only include substantial content
                sections.append(element)
        
        return sections
    
    def _enhance_text_section(self, section) -> str:
        """
        Enhance text section with Markdown formatting for key financial data
        """
        text = section.get_text().strip()
        
        if len(text) < 100:
            return ""
        
        # Add bold formatting for financial amounts
        text = re.sub(
            r'\$([0-9,]+(?:\.[0-9]+)?)\s*(million|billion|M|B)?',
            r'**$\1\2**',
            text
        )
        
        # Add bold formatting for percentages
        text = re.sub(
            r'([0-9]+(?:\.[0-9]+)?%)',
            r'**\1**',
            text
        )
        
        # Add bold formatting for key dates
        text = re.sub(
            r'(fiscal\s+year\s+\d{4}|quarter\s+ended\s+\w+\s+\d+,\s+\d{4})',
            r'**\1**',
            text,
            flags=re.IGNORECASE
        )
        
        # Extract section title if present
        section_title = self._extract_section_title(section)
        if section_title:
            text = f"## {section_title}\n\n{text}"
        
        return text
    
    def _extract_section_title(self, section) -> Optional[str]:
        """
        Extract section title from HTML element
        """
        # Look for preceding header elements
        prev_sibling = section.find_previous_sibling()
        while prev_sibling:
            if prev_sibling.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                title = prev_sibling.get_text().strip()
                if len(title) < 100:  # Reasonable title length
                    return title
            prev_sibling = prev_sibling.find_previous_sibling()
        
        # Look for bold text at the beginning of the section
        first_bold = section.find(['b', 'strong'])
        if first_bold:
            title = first_bold.get_text().strip()
            if len(title) < 100:
                return title
        
        return None
    
    def _generate_enhanced_markdown_from_text(self, text: str, filing_type: str) -> str:
        """
        Generate enhanced Markdown from plain text (for TXT files)
        """
        # Split into paragraphs
        paragraphs = text.split('\n\n')
        enhanced_paragraphs = []
        
        for para in paragraphs:
            if len(para.strip()) < 50:
                continue
                
            # Enhance with financial data markup
            enhanced_para = self._enhance_text_with_markdown(para)
            enhanced_paragraphs.append(enhanced_para)
        
        return '\n\n'.join(enhanced_paragraphs)
    
    def _enhance_text_with_markdown(self, text: str) -> str:
        """
        Enhance text with Markdown formatting for financial data
        """
        # Add bold formatting for financial amounts
        text = re.sub(
            r'\$([0-9,]+(?:\.[0-9]+)?)\s*(million|billion|M|B)?',
            r'**$\1\2**',
            text
        )
        
        # Add bold formatting for percentages
        text = re.sub(
            r'([0-9]+(?:\.[0-9]+)?%)',
            r'**\1**',
            text
        )
        
        return text
    
    def _identify_filing_type_enhanced(self, text: str) -> str:
        """
        Enhanced filing type identification using multiple patterns and scoring
        """
        if not text:
            return 'UNKNOWN'
            
        # Expand search range
        search_text = text[:20000] if len(text) > 20000 else text
        search_text_upper = search_text.upper()
        
        # Score each filing type
        scores = {}
        
        for filing_type, patterns in self.filing_patterns.items():
            score = 0
            matches = []
            
            for pattern, weight in patterns:
                if re.search(pattern, search_text_upper):
                    score += weight
                    matches.append(pattern)
            
            if score > 0:
                scores[filing_type] = score
                logger.debug(f"{filing_type} score: {score}, matches: {matches}")
        
        # Return the filing type with highest score
        if scores:
            best_type = max(scores.items(), key=lambda x: x[1])[0]
            logger.info(f"Filing type identified as {best_type} with score {scores[best_type]}")
            return best_type
        
        # Fallback: check for any item patterns (might be 8-K)
        if re.search(r'Item\s+\d+\.\d+', search_text_upper):
            logger.info("Found Item pattern, assuming 8-K")
            return '8-K'
        
        logger.warning("Could not identify filing type, defaulting to UNKNOWN")
        return 'UNKNOWN'
    
    def _extract_sections_by_type(self, text: str, filing_type: str) -> Dict[str, str]:
        """
        Extract sections based on identified filing type
        """
        if not text:
            return {'primary_content': ''}
            
        if filing_type == '8-K':
            return self._extract_8k_sections_enhanced(text)
        elif filing_type == '10-K':
            return self._extract_10k_sections_enhanced(text)
        elif filing_type == '10-Q':
            return self._extract_10q_sections_enhanced(text)
        elif filing_type == 'S-1':
            return self._extract_s1_sections_enhanced(text)
        else:
            return {'primary_content': text[:50000] if text else ''}
    
    def _extract_smart_content(self, text: str, filing_type: str) -> str:
        """
        Smart content extraction when standard methods fail
        Prioritizes content-rich sections
        """
        if not text:
            return ''
            
        logger.info(f"Using smart content extraction for {filing_type}")
        
        # Find content-dense areas
        paragraphs = text.split('\n\n')
        scored_paragraphs = []
        
        # Keywords indicating valuable content
        value_keywords = [
            'revenue', 'income', 'earnings', 'financial', 'business', 'operations',
            'management', 'discussion', 'analysis', 'risk', 'factors', 'results',
            'quarter', 'year', 'growth', 'decrease', 'increase', 'million', 'billion'
        ]
        
        # Add filing-specific keywords
        if filing_type == 'S-1':
            value_keywords.extend([
                'offering', 'proceeds', 'shares', 'ipo', 'registration',
                'prospectus', 'underwriting', 'market', 'competitive', 'strategy'
            ])
        elif filing_type == '10-K':
            value_keywords.extend([
                'annual', 'fiscal', 'consolidated', 'comprehensive', 'segment'
            ])
        elif filing_type == '10-Q':
            value_keywords.extend([
                'quarterly', 'three months', 'nine months', 'interim'
            ])
        
        for para in paragraphs:
            if len(para) < 100:  # Skip short paragraphs
                continue
                
            score = 0
            para_lower = para.lower()
            
            # Score based on keyword presence
            for keyword in value_keywords:
                score += para_lower.count(keyword) * 2
            
            # Bonus for financial numbers
            score += len(re.findall(r'\$[\d,]+', para)) * 3
            score += len(re.findall(r'\d+\.\d+%', para)) * 3
            
            # Bonus for section headers
            if re.search(r'^[A-Z][A-Z\s]{5,}$', para.split('\n')[0]):
                score += 10
            
            # Penalty for legal boilerplate
            if any(term in para_lower for term in ['pursuant to', 'securities act', 'incorporated by reference']):
                score -= 5
            
            scored_paragraphs.append((score, para))
        
        # Sort by score and take the best content
        scored_paragraphs.sort(key=lambda x: x[0], reverse=True)
        
        # Build content from highest-scoring paragraphs
        smart_content = []
        total_length = 0
        
        for score, para in scored_paragraphs:
            if total_length + len(para) > 80000:  # Respect token limits
                break
            if score > 0:  # Only include paragraphs with positive scores
                smart_content.append(para)
                total_length += len(para)
        
        result = '\n\n'.join(smart_content)
        logger.info(f"Smart extraction yielded {len(result)} chars from {len(scored_paragraphs)} paragraphs")
        
        return result if result else text[:50000]  # Fallback
    
    def _extract_8k_sections_enhanced(self, text: str) -> Dict[str, str]:
        """
        Enhanced 8-K extraction with better Item detection
        """
        sections = {}
        items = []
        
        # More flexible Item patterns
        item_patterns = [
            r'Item\s+(\d+\.\d+)\s*[:\-\s]*([^\n]{0,200})',
            r'ITEM\s+(\d+\.\d+)\s*[:\-\s]*([^\n]{0,200})',
        ]
        
        all_matches = []
        
        for pattern in item_patterns:
            matches = list(re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE))
            all_matches.extend(matches)
        
        # Remove duplicates by position
        unique_matches = []
        seen_positions = set()
        
        for match in all_matches:
            pos = match.start()
            if not any(abs(pos - p) < 50 for p in seen_positions):
                unique_matches.append(match)
                seen_positions.add(pos)
        
        # Sort by position
        unique_matches.sort(key=lambda m: m.start())
        
        logger.info(f"Found {len(unique_matches)} unique Item references in 8-K")
        
        # Extract each item's content
        for i, match in enumerate(unique_matches):
            item_num = match.group(1)
            item_title = match.group(2) if match.lastindex >= 2 else ""
            
            # Find content boundaries
            start_pos = match.end()
            
            # End position is either next item or signature section
            if i + 1 < len(unique_matches):
                end_pos = unique_matches[i + 1].start()
            else:
                # Look for signature section
                sig_match = re.search(r'SIGNATURES?|Pursuant\s+to\s+the\s+requirements', text[start_pos:], re.IGNORECASE)
                if sig_match:
                    end_pos = start_pos + sig_match.start()
                else:
                    end_pos = min(start_pos + 15000, len(text))
            
            # Extract content
            item_content = text[start_pos:end_pos].strip()
            
            # Clean up
            item_content = re.sub(r'\s+', ' ', item_content)
            
            # Only include substantial content
            if len(item_content) > 50:
                item_header = f"Item {item_num}"
                if item_title:
                    item_header += f" - {item_title.strip()}"
                
                formatted_item = f"\n{item_header}\n{'-' * len(item_header)}\n{item_content}"
                items.append(formatted_item)
                logger.debug(f"Extracted {item_header}: {len(item_content)} chars")
        
        if items:
            sections['items_content'] = '\n\n'.join(items)
            sections['primary_content'] = sections['items_content']
            logger.info(f"Successfully extracted {len(items)} items from 8-K")
        
        return sections
    
    def _extract_10k_sections_enhanced(self, text: str) -> Dict[str, str]:
        """
        Enhanced 10-K extraction focusing on key business sections
        """
        sections = {}
        combined_content = []
        
        # Extract each key section
        for section_name, section_info in self.key_sections['10-K'].items():
            pattern = section_info['pattern']
            max_chars = section_info['max_chars']
            
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start = match.start()
                end = min(start + max_chars, len(text))
                
                # Find the next major section to avoid overrun
                next_section = re.search(r'Item\s+\d+[A-Z]?[.\s]', text[start + 100:end])
                if next_section:
                    end = start + 100 + next_section.start()
                
                section_text = text[start:end]
                
                if len(section_text) > 500:
                    header = f"\n{'='*50}\n{section_name}\n{'='*50}\n"
                    combined_content.append(header + section_text)
                    logger.info(f"Extracted {section_name} from 10-K: {len(section_text)} chars")
        
        if combined_content:
            sections['primary_content'] = '\n\n'.join(combined_content)
        
        # Also extract financial highlights if present
        fin_match = re.search(r'Financial\s+Highlights|Selected\s+Financial\s+Data', text, re.IGNORECASE)
        if fin_match:
            fin_start = fin_match.start()
            fin_section = text[fin_start:fin_start + 10000]
            sections['financial_highlights'] = fin_section
        
        return sections
    
    def _extract_10q_sections_enhanced(self, text: str) -> Dict[str, str]:
        """
        Enhanced 10-Q extraction focusing on quarterly results
        """
        sections = {}
        combined_content = []
        
        # Extract each key section
        for section_name, section_info in self.key_sections['10-Q'].items():
            pattern = section_info['pattern']
            max_chars = section_info['max_chars']
            
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start = match.start()
                end = min(start + max_chars, len(text))
                
                # Find the next major section
                next_section = re.search(r'(?:Part|PART|Item|ITEM)\s+[IVX\d]+', text[start + 100:end])
                if next_section:
                    end = start + 100 + next_section.start()
                
                section_text = text[start:end]
                
                if len(section_text) > 500:
                    header = f"\n{'='*50}\n{section_name}\n{'='*50}\n"
                    combined_content.append(header + section_text)
                    logger.info(f"Extracted {section_name} from 10-Q: {len(section_text)} chars")
        
        if combined_content:
            sections['primary_content'] = '\n\n'.join(combined_content)
        
        # Extract recent quarter results
        quarter_match = re.search(r'Three\s+Months\s+Ended|Quarter\s+Ended', text, re.IGNORECASE)
        if quarter_match:
            results_start = quarter_match.start()
            results_section = text[results_start:results_start + 15000]
            sections['quarterly_results'] = results_section
        
        return sections
    
    def _extract_s1_sections_enhanced(self, text: str) -> Dict[str, str]:
        """
        Enhanced S-1 extraction with intelligent chapter detection
        Uses multiple methods: TOC extraction, pattern matching, and smart content detection
        """
        sections = {}
        
        # Method 1: Try to extract table of contents
        toc = self._extract_s1_table_of_contents(text)
        if toc:
            logger.info(f"Found S-1 table of contents with {len(toc)} entries")
            toc_sections = self._extract_sections_from_toc(text, toc)
            if toc_sections:
                sections.update(toc_sections)
        
        # Method 2: Use pattern-based extraction for critical sections
        pattern_sections = self._extract_s1_by_patterns(text)
        
        # Merge pattern sections with TOC sections (TOC takes precedence)
        for section_name, content in pattern_sections.items():
            if section_name not in sections or len(content) > len(sections.get(section_name, '')):
                sections[section_name] = content
        
        # Method 3: Ensure we have all critical content
        critical_content = []
        
        # Prioritize sections based on importance
        section_priority = sorted(self.s1_critical_sections.items(), 
                                key=lambda x: x[1]['priority'], reverse=True)
        
        for section_name, _ in section_priority:
            if section_name in sections and len(sections[section_name]) > 100:
                header = f"\n{'='*50}\n{section_name}\n{'='*50}\n"
                critical_content.append(header + sections[section_name])
        
        if critical_content:
            sections['primary_content'] = '\n\n'.join(critical_content)
            logger.info(f"Successfully extracted {len(critical_content)} critical sections from S-1")
        else:
            # Fallback to smart content extraction
            logger.warning("Using fallback extraction for S-1")
            sections['primary_content'] = self._extract_smart_content(text, 'S-1')
        
        # Extract key financial metrics if available
        financial_data = self._extract_s1_financial_metrics(text)
        if financial_data:
            sections['financial_summary'] = financial_data
        
        # Extract offering details
        offering_details = self._extract_s1_offering_details(text)
        if offering_details:
            sections['offering_details'] = offering_details
        
        return sections
    
    def _extract_s1_table_of_contents(self, text: str) -> Optional[Dict[str, int]]:
        """
        Extract table of contents from S-1 document
        """
        toc = {}
        
        # Look for table of contents patterns
        toc_patterns = [
            r'TABLE\s+OF\s+CONTENTS',
            r'CONTENTS',
            r'INDEX'
        ]
        
        toc_start = None
        for pattern in toc_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                toc_start = match.end()
                break
        
        if not toc_start:
            return None
        
        # Extract TOC entries
        toc_section = text[toc_start:toc_start + 5000]
        
        # Pattern for TOC entries
        toc_entry_pattern = r'([A-Z][A-Z\s\',\-&]+?)[\s\.]+(\d+)\s*$'
        
        for line in toc_section.split('\n'):
            match = re.match(toc_entry_pattern, line.strip())
            if match:
                section_name = match.group(1).strip()
                page_num = int(match.group(2))
                
                # Only include relevant sections
                for critical_section in self.s1_critical_sections:
                    if critical_section.upper() in section_name.upper():
                        toc[section_name] = page_num
                        break
        
        return toc if toc else None
    
    def _extract_sections_from_toc(self, text: str, toc: Dict[str, int]) -> Dict[str, str]:
        """
        Extract sections based on table of contents
        """
        sections = {}
        
        # Sort TOC by page number
        sorted_toc = sorted(toc.items(), key=lambda x: x[1])
        
        for i, (section_name, page_num) in enumerate(sorted_toc):
            # Try to find section start
            section_patterns = []
            
            # Add patterns based on section name
            clean_name = re.escape(section_name)
            section_patterns.append(rf'{clean_name}')
            space_pattern = clean_name.replace(" ", r"\s+")
            section_patterns.append(space_pattern)
            
            section_start = None
            for pattern in section_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    section_start = match.start()
                    break
            
            if section_start:
                # Determine section end
                if i + 1 < len(sorted_toc):
                    # Look for next section
                    next_section_name = sorted_toc[i + 1][0]
                    next_match = re.search(re.escape(next_section_name), text[section_start:], re.IGNORECASE)
                    if next_match:
                        section_end = section_start + next_match.start()
                    else:
                        section_end = section_start + 50000
                else:
                    section_end = min(section_start + 50000, len(text))
                
                section_content = text[section_start:section_end]
                
                # Clean and validate content
                if len(section_content) > 100:
                    sections[section_name] = self._clean_text(section_content)
                    logger.info(f"Extracted {section_name} from TOC: {len(section_content)} chars")
        
        return sections
    
    def _extract_s1_by_patterns(self, text: str) -> Dict[str, str]:
        """
        Extract S-1 sections using pattern matching
        """
        sections = {}
        
        for section_name, section_config in self.s1_critical_sections.items():
            patterns = section_config['patterns']
            keywords = section_config['keywords']
            
            # Try each pattern
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    start = match.start()
                    
                    # Look for section end markers
                    end = self._find_section_end(text, start, section_name)
                    
                    section_content = text[start:end]
                    
                    # Validate content has relevant keywords
                    content_lower = section_content.lower()
                    keyword_matches = sum(1 for kw in keywords if kw in content_lower)
                    
                    if keyword_matches >= 1 and len(section_content) > 200:
                        sections[section_name] = self._clean_text(section_content)
                        logger.info(f"Extracted {section_name} by pattern: {len(section_content)} chars")
                        break
        
        return sections
    
    def _extract_s1_from_html_structure(self, soup: BeautifulSoup) -> Dict[str, str]:
        """
        Extract S-1 sections using HTML structure and styling
        """
        sections = {}
        
        # Look for sections by font styling
        headers = []
        
        # Find potential headers by various methods
        # Method 1: Bold tags
        for bold in soup.find_all(['b', 'strong']):
            text = bold.get_text().strip()
            if len(text) > 5 and text.isupper():
                headers.append((bold, text))
        
        # Method 2: Font tags with specific styles
        for font in soup.find_all('font'):
            if font.get('size') and int(font.get('size', 0)) > 3:
                text = font.get_text().strip()
                if text:
                    headers.append((font, text))
        
        # Method 3: Divs or P tags with style attributes
        for tag in soup.find_all(['div', 'p']):
            style = tag.get('style', '')
            if 'bold' in style or 'font-weight' in style:
                text = tag.get_text().strip()
                if text and len(text) > 5:
                    headers.append((tag, text))
        
        # Process headers to find critical sections
        for header_tag, header_text in headers:
            header_upper = header_text.upper()
            
            for section_name, config in self.s1_critical_sections.items():
                # Check if header matches any critical section
                if any(pattern in header_upper for pattern in [section_name.upper()] + [kw.upper() for kw in config['keywords'][:2]]):
                    # Extract content after this header
                    content = []
                    current = header_tag.find_next_sibling()
                    
                    while current and len('\n'.join(content)) < 30000:
                        # Stop if we hit another header
                        if current.name in ['b', 'strong'] and current.get_text().strip().isupper():
                            break
                        
                        text = current.get_text().strip()
                        if text:
                            content.append(text)
                        
                        current = current.find_next_sibling()
                    
                    if content:
                        section_content = '\n\n'.join(content)
                        if len(section_content) > 200:
                            sections[section_name] = section_content
                            logger.info(f"Extracted {section_name} from HTML structure: {len(section_content)} chars")
        
        return sections
    
    def _extract_s1_financial_metrics(self, text: str) -> Optional[str]:
        """
        Extract key financial metrics from S-1
        """
        financial_section = ""
        
        # Look for financial data sections
        patterns = [
            r'SELECTED\s+FINANCIAL\s+DATA',
            r'FINANCIAL\s+HIGHLIGHTS',
            r'KEY\s+FINANCIAL\s+METRICS',
            r'SUMMARY\s+FINANCIAL\s+INFORMATION'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start = match.start()
                end = min(start + 15000, len(text))
                
                # Extract financial section
                fin_text = text[start:end]
                
                # Look for key metrics
                metrics = []
                
                # Revenue patterns
                rev_patterns = [
                    r'revenue[s]?\s*:?\s*\$?([\d,]+(?:\.\d+)?)\s*(?:million|billion)?',
                    r'total\s+revenue[s]?\s*:?\s*\$?([\d,]+(?:\.\d+)?)',
                ]
                
                for rev_pattern in rev_patterns:
                    rev_match = re.search(rev_pattern, fin_text, re.IGNORECASE)
                    if rev_match:
                        metrics.append(f"Revenue: ${rev_match.group(1)}")
                
                # Growth patterns
                growth_match = re.search(r'growth\s+rate\s*:?\s*([\d.]+)%', fin_text, re.IGNORECASE)
                if growth_match:
                    metrics.append(f"Growth Rate: {growth_match.group(1)}%")
                
                # Loss/Income patterns
                loss_match = re.search(r'net\s+(?:loss|income)\s*:?\s*\$?([\d,]+(?:\.\d+)?)', fin_text, re.IGNORECASE)
                if loss_match:
                    metrics.append(f"Net Loss/Income: ${loss_match.group(1)}")
                
                if metrics:
                    financial_section = "Key Financial Metrics:\n" + '\n'.join(metrics) + f"\n\nSource:\n{fin_text[:2000]}"
                    break
        
        return financial_section if financial_section else None
    
    def _extract_s1_offering_details(self, text: str) -> Optional[str]:
        """
        Extract IPO offering details from S-1
        """
        offering_details = ""
        
        # Look for offering section
        offering_match = re.search(r'THE\s+OFFERING', text, re.IGNORECASE)
        if offering_match:
            start = offering_match.start()
            section = text[start:start + 10000]
            
            details = []
            
            # Share price range
            price_match = re.search(r'price\s+range[^$]*\$?([\d.]+)\s*to\s*\$?([\d.]+)', section, re.IGNORECASE)
            if price_match:
                details.append(f"Price Range: ${price_match.group(1)} - ${price_match.group(2)}")
            
            # Number of shares
            shares_match = re.search(r'([\d,]+)\s+shares?\s+of\s+common\s+stock', section, re.IGNORECASE)
            if shares_match:
                details.append(f"Shares Offered: {shares_match.group(1)}")
            
            # Use of proceeds
            proceeds_match = re.search(r'use\s+of\s+proceeds[^.]*\.([^.]+\.)', section, re.IGNORECASE)
            if proceeds_match:
                details.append(f"Use of Proceeds: {proceeds_match.group(1).strip()}")
            
            if details:
                offering_details = "Offering Details:\n" + '\n'.join(details)
        
        return offering_details if offering_details else None
    
    def _find_section_end(self, text: str, start_pos: int, current_section: str) -> int:
        """
        Find the end position of a section
        """
        # Look for next major section
        remaining_text = text[start_pos:]
        
        # Common section end markers
        end_patterns = [
            r'\n[A-Z][A-Z\s]{10,}\n',  # All caps header
            r'={5,}',  # Separator line
            r'-{5,}',  # Separator line
        ]
        
        # Also look for next critical section
        for section_name in self.s1_critical_sections:
            if section_name != current_section:
                for pattern in self.s1_critical_sections[section_name]['patterns']:
                    end_patterns.append(pattern)
        
        min_end_pos = len(text)
        for pattern in end_patterns:
            match = re.search(pattern, remaining_text[1000:])  # Skip first 1000 chars
            if match:
                end_pos = start_pos + 1000 + match.start()
                if end_pos < min_end_pos:
                    min_end_pos = end_pos
        
        # Cap at reasonable length
        return min(min_end_pos, start_pos + 50000)
    
    def _extract_from_ixbrl(self, html_content: str, pre_identified_type: str = None) -> Dict[str, str]:
        """
        Enhanced iXBRL extraction with better content preservation and Markdown enhancement
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove all ix: namespace elements' tags but keep their text
        for elem in soup.find_all(re.compile(r'^ix:', re.I)):
            elem.unwrap()
        
        # Remove script and style
        for element in soup(['script', 'style', 'link', 'meta', 'noscript']):
            element.decompose()
        
        # Extract enhanced content with Markdown
        enhanced_text = self._extract_enhanced_content_from_soup(soup)
        
        # Extract text with structure preservation
        text_parts = []
        
        # Process body content
        body = soup.find('body')
        if body:
            # Walk through all elements
            for element in body.descendants:
                if isinstance(element, str):
                    text = element.strip()
                    if text and not text.isspace():
                        text_parts.append(text)
                elif element.name in ['div', 'p', 'br', 'h1', 'h2', 'h3']:
                    # Add spacing for structure
                    text_parts.append('\n')
        
        # Join and clean
        text = ' '.join(text_parts)
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = text.strip()
        
        logger.info(f"Extracted {len(text)} chars from iXBRL")
        
        # Use pre-identified type if available
        filing_type = pre_identified_type if pre_identified_type and pre_identified_type != 'UNKNOWN' else self._identify_filing_type_enhanced(text)
        logger.info(f"Processing iXBRL as {filing_type}")
        
        # Extract sections based on type
        sections = self._extract_sections_by_type(text, filing_type)
        
        # Always include full text and filing type
        sections['full_text'] = text
        sections['enhanced_text'] = enhanced_text  # NEW: Markdown enhanced text
        sections['filing_type'] = filing_type
        
        # Ensure primary content
        if 'primary_content' not in sections or len(sections.get('primary_content', '')) < 1000:
            sections['primary_content'] = self._extract_smart_content(text, filing_type)
        
        return sections
    
    def _extract_all_text_content(self, soup: BeautifulSoup) -> str:
        """
        Alternative extraction method for difficult documents
        """
        texts = []
        
        for element in soup.descendants:
            if isinstance(element, str) and element.strip():
                texts.append(element.strip())
        
        return ' '.join(texts)
    
    def _clean_text(self, text: str) -> str:
        """
        Clean extracted text
        """
        # Remove excessive whitespace but preserve some structure
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Reduce multiple newlines
        text = re.sub(r'[ \t]+', ' ', text)  # Reduce multiple spaces/tabs
        
        # Remove special characters that might interfere
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        
        # Remove repeated underscores or dashes
        text = re.sub(r'[_\-]{4,}', '', text)
        
        # Remove excessive dots
        text = re.sub(r'\.{4,}', '...', text)
        
        return text.strip()
    
    def extract_financial_tables(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extract financial tables from HTML - ENHANCED with Markdown conversion
        """
        tables = []
        
        # Look for tables with financial keywords
        financial_keywords = ['revenue', 'income', 'assets', 'liabilities', 'cash', 'earnings']
        
        for table in soup.find_all('table'):
            table_text = table.get_text().lower()
            if any(keyword in table_text for keyword in financial_keywords):
                # Extract table data with Markdown conversion
                markdown_table = self._table_to_markdown_clean(table)
                
                if markdown_table:
                    tables.append({
                        'markdown': markdown_table,
                        'text': table.get_text(),
                        'type': 'financial'
                    })
        
        return tables


# Create singleton instance
text_extractor = TextExtractor()
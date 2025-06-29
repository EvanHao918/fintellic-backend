# app/services/text_extractor.py
"""
Text Extractor Service
Extracts structured text from SEC filing HTML documents
Enhanced for different filing types (10-K, 10-Q, 8-K, S-1)
"""
import re
from pathlib import Path
from typing import Dict, Optional, List
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


class TextExtractor:
    """
    Extract structured text from SEC filing HTML documents
    """
    
    def __init__(self):
        self.min_section_length = 100  # Minimum characters for a valid section
        self.max_section_length = 50000  # Maximum characters to avoid memory issues
    
    def extract_from_filing(self, filing_dir: Path) -> Dict[str, str]:
        """
        Extract text from all documents in a filing directory
        
        Args:
            filing_dir: Path to the filing directory
            
        Returns:
            Dictionary with extracted text sections
        """
        # First, check if we have a TXT file (preferred)
        txt_files = list(filing_dir.glob("*.txt"))
        if txt_files:
            txt_file = txt_files[0]  # Use first TXT file
            logger.info(f"Found TXT file, using {txt_file.name}")
            return self.extract_from_txt(txt_file)
        
        # Otherwise, find the main HTML document (not index.htm)
        html_files = [f for f in filing_dir.glob("*.htm") if f.name != "index.htm"]
        html_files.extend([f for f in filing_dir.glob("*.html") if f.name != "index.html"])
        
        if not html_files:
            logger.warning(f"No filing documents found in {filing_dir}")
            return {'error': 'No filing documents found'}
        
        # Use the first non-index HTML file
        main_doc = html_files[0]
        logger.info(f"Extracting text from {main_doc.name}")
        
        return self.extract_from_html(main_doc)
    
    def extract_from_txt(self, txt_path: Path) -> Dict[str, str]:
        """
        Extract text from SEC TXT filing
        
        Args:
            txt_path: Path to the TXT file
            
        Returns:
            Dictionary with extracted text
        """
        try:
            with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Remove SEC document headers
            # Find the end of header section (usually marked by </SEC-HEADER>)
            header_end = content.find('</SEC-HEADER>')
            if header_end != -1:
                content = content[header_end + len('</SEC-HEADER>'):]
            
            # Remove HTML/XML tags if present
            content = re.sub(r'<[^>]+>', ' ', content)
            
            # Find the main document section (between <DOCUMENT> and </DOCUMENT>)
            doc_start = content.find('<DOCUMENT>')
            doc_end = content.find('</DOCUMENT>')
            
            if doc_start != -1 and doc_end != -1:
                # Extract just the first document (the main filing)
                main_content = content[doc_start:doc_end]
            else:
                main_content = content
            
            # Clean up the text
            main_content = self._clean_text(main_content)
            
            # Identify filing type
            filing_type = self._identify_filing_type(main_content)
            
            # Extract sections based on filing type
            if filing_type == '8-K':
                sections = self._extract_8k_sections_from_text(main_content)
            elif filing_type == '10-K':
                sections = self._extract_10k_sections_from_text(main_content)
            elif filing_type == '10-Q':
                sections = self._extract_10q_sections_from_text(main_content)
            elif filing_type == 'S-1':
                sections = self._extract_s1_sections_from_text(main_content)
            else:
                sections = {}
            
            # Always include full text and primary content
            sections['full_text'] = main_content
            sections['primary_content'] = sections.get('primary_content', main_content[:50000])
            
            return sections
            
        except Exception as e:
            logger.error(f"Error extracting from TXT file {txt_path}: {e}")
            return {'error': str(e)}
    
    def _identify_filing_type(self, text: str) -> str:
        """Identify the filing type from text content"""
        text_upper = text.upper()[:5000]  # Check first 5000 chars
        
        if 'FORM 10-K' in text_upper or 'ANNUAL REPORT' in text_upper:
            return '10-K'
        elif 'FORM 10-Q' in text_upper or 'QUARTERLY REPORT' in text_upper:
            return '10-Q'
        elif 'FORM 8-K' in text_upper or 'CURRENT REPORT' in text_upper:
            return '8-K'
        elif 'FORM S-1' in text_upper or 'REGISTRATION STATEMENT' in text_upper:
            return 'S-1'
        else:
            return 'UNKNOWN'
    
    def _extract_8k_sections_from_text(self, text: str) -> Dict[str, str]:
        """
        Extract specific items from 8-K text
        """
        sections = {}
        
        # Look for ITEM patterns in 8-K
        # Common patterns: "Item 8.01", "ITEM 8.01", "Item 8.01 Other Events"
        item_pattern = re.compile(r'(ITEM\s+\d+\.\d+[^\n]*)', re.IGNORECASE)
        
        items = []
        matches = list(item_pattern.finditer(text))
        
        for i, match in enumerate(matches):
            item_header = match.group(1)
            start_pos = match.end()
            
            # Find the end position (either next item or signature section)
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                # Look for signature section or end
                sig_pos = text.find('SIGNATURES', start_pos)
                if sig_pos != -1:
                    end_pos = sig_pos
                else:
                    end_pos = min(start_pos + 10000, len(text))  # Max 10k chars per item
            
            # Extract item content
            item_content = text[start_pos:end_pos].strip()
            
            # Only include if there's substantial content
            if len(item_content) > 50:
                items.append(f"\n{item_header}\n{'-' * len(item_header)}\n{item_content}")
        
        if items:
            sections['items_content'] = '\n\n'.join(items)
            sections['primary_content'] = sections['items_content']
        
        return sections
    
    def _extract_10k_sections_from_text(self, text: str) -> Dict[str, str]:
        """
        Extract key sections from 10-K text
        """
        sections = {}
        
        # Key sections to look for in 10-K
        section_patterns = {
            'business': r'(?:ITEM\s+1[.\s]+BUSINESS|PART\s+I[.\s]+ITEM\s+1)',
            'risk_factors': r'(?:ITEM\s+1A[.\s]+RISK\s+FACTORS)',
            'mda': r'(?:ITEM\s+7[.\s]+MANAGEMENT.S\s+DISCUSSION)',
            'financial_statements': r'(?:ITEM\s+8[.\s]+FINANCIAL\s+STATEMENTS)'
        }
        
        combined_sections = []
        
        for section_name, pattern in section_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start = match.start()
                # Extract up to 20k chars from this section
                section_text = text[start:start + 20000]
                if len(section_text) > 500:
                    combined_sections.append(section_text)
        
        if combined_sections:
            sections['primary_content'] = '\n\n'.join(combined_sections)
        
        return sections
    
    def _extract_10q_sections_from_text(self, text: str) -> Dict[str, str]:
        """
        Extract key sections from 10-Q text
        """
        sections = {}
        
        # Focus on financial data and MD&A for quarterly reports
        section_patterns = {
            'financial_statements': r'(?:FINANCIAL\s+STATEMENTS|CONDENSED\s+CONSOLIDATED)',
            'mda': r'(?:MANAGEMENT.S\s+DISCUSSION\s+AND\s+ANALYSIS)'
        }
        
        combined_sections = []
        
        for section_name, pattern in section_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start = match.start()
                section_text = text[start:start + 25000]  # More content for quarterly
                if len(section_text) > 500:
                    combined_sections.append(section_text)
        
        if combined_sections:
            sections['primary_content'] = '\n\n'.join(combined_sections)
        
        return sections
    
    def _extract_s1_sections_from_text(self, text: str) -> Dict[str, str]:
        """
        Extract key sections from S-1 text
        """
        sections = {}
        
        # Key sections for IPO filings
        section_patterns = {
            'summary': r'(?:PROSPECTUS\s+SUMMARY|SUMMARY)',
            'risk_factors': r'(?:RISK\s+FACTORS)',
            'use_of_proceeds': r'(?:USE\s+OF\s+PROCEEDS)',
            'business': r'(?:BUSINESS|OUR\s+BUSINESS)'
        }
        
        combined_sections = []
        
        for section_name, pattern in section_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start = match.start()
                section_text = text[start:start + 15000]
                if len(section_text) > 500:
                    combined_sections.append(section_text)
        
        if combined_sections:
            sections['primary_content'] = '\n\n'.join(combined_sections)
        
        return sections
    
    def extract_from_html(self, html_path: Path) -> Dict[str, str]:
        """
        Extract structured text sections from an HTML filing
        
        Args:
            html_path: Path to the HTML file
            
        Returns:
            Dictionary with keys: 'full_text', 'primary_content'
        """
        try:
            with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            
            # Check if this is an iXBRL document
            if 'ix:' in html_content or 'inline XBRL' in html_content.lower():
                logger.info("Detected iXBRL document, using special extraction")
                return self._extract_from_ixbrl(html_content)
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for element in soup(['script', 'style', 'link', 'meta']):
                element.decompose()
            
            # Extract text
            text = soup.get_text()
            
            # Clean up text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            # If text is too short, try alternative extraction
            if len(text) < 500:
                logger.warning(f"Extracted text too short ({len(text)} chars), trying alternative methods")
                text = self._extract_all_text_content(soup)
            
            # Identify filing type
            filing_type = self._identify_filing_type(text)
            
            # Extract sections based on filing type
            if filing_type == '8-K':
                sections = self._extract_8k_sections(soup, text)
            elif filing_type == '10-K':
                sections = self._extract_10k_sections(soup, text)
            elif filing_type == '10-Q':
                sections = self._extract_10q_sections(soup, text)
            elif filing_type == 'S-1':
                sections = self._extract_s1_sections(soup, text)
            else:
                sections = {'full_text': text, 'primary_content': text[:50000]}
            
            # Always ensure we have these keys
            if 'full_text' not in sections:
                sections['full_text'] = text
            if 'primary_content' not in sections:
                sections['primary_content'] = text[:50000]
            
            return sections
            
        except Exception as e:
            logger.error(f"Error extracting text from {html_path}: {e}")
            return {'error': str(e)}
    
    def _extract_from_ixbrl(self, html_content: str) -> Dict[str, str]:
        """
        Extract text from iXBRL (inline XBRL) documents
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove all ix: namespace elements' tags but keep their text
        for elem in soup.find_all(re.compile(r'^ix:', re.I)):
            elem.unwrap()
        
        # Remove script and style
        for element in soup(['script', 'style', 'link', 'meta']):
            element.decompose()
        
        # Look for the main content in various possible containers
        main_content = None
        
        # Try different selectors for iXBRL documents
        selectors = [
            {'name': 'body'},
            {'name': 'div', 'attrs': {'class': re.compile('document', re.I)}},
            {'name': 'div', 'attrs': {'id': re.compile('document', re.I)}},
            {'name': 'table'},
        ]
        
        for selector in selectors:
            elements = soup.find_all(**selector)
            if elements:
                # Get the element with the most text content
                main_content = max(elements, key=lambda e: len(e.get_text()))
                if len(main_content.get_text()) > 500:
                    break
        
        if main_content:
            text = main_content.get_text()
        else:
            text = soup.get_text()
        
        # Clean the text
        text = self._clean_text(text)
        
        return {
            'full_text': text,
            'primary_content': text[:50000]  # Use first 50k chars as primary
        }
    
    def _extract_all_text_content(self, soup: BeautifulSoup) -> str:
        """
        Alternative extraction method for difficult documents
        """
        # Get all text nodes
        texts = []
        
        for element in soup.descendants:
            if isinstance(element, str) and element.strip():
                texts.append(element.strip())
        
        return ' '.join(texts)
    
    def _extract_8k_sections(self, soup: BeautifulSoup, full_text: str) -> Dict[str, str]:
        """
        Extract specific sections from 8-K filing
        """
        sections = {
            'full_text': full_text,
            'primary_content': ''
        }
        
        # Try to find the main content area
        # Look for common patterns in 8-K filings
        
        # Method 1: Look for Item sections
        item_pattern = re.compile(r'Item\s+\d+\.\d+', re.IGNORECASE)
        items_found = []
        
        for element in soup.find_all(text=item_pattern):
            parent = element.parent
            if parent:
                # Get the text content after this item header
                content = []
                for sibling in parent.find_next_siblings():
                    if sibling.name and item_pattern.search(sibling.get_text()):
                        break  # Stop at next item
                    content.append(sibling.get_text())
                
                item_text = ' '.join(content)
                if len(item_text) > 50:  # Only include substantial content
                    items_found.append(f"{element.strip()}: {item_text}")
        
        # Method 2: Look for the main document div/table
        main_content = soup.find('div', {'class': 'document'})
        if not main_content:
            # Try to find the largest text block
            all_divs = soup.find_all('div')
            if all_divs:
                main_content = max(all_divs, key=lambda d: len(d.get_text()))
        
        if main_content:
            sections['primary_content'] = self._clean_text(main_content.get_text())
        elif items_found:
            sections['primary_content'] = '\n\n'.join(items_found)
        else:
            # Fallback: use the full text
            sections['primary_content'] = full_text[:10000]  # First 10k characters
        
        return sections
    
    def _extract_10k_sections(self, soup: BeautifulSoup, full_text: str) -> Dict[str, str]:
        """Extract sections from 10-K filing"""
        sections = {
            'full_text': full_text,
            'primary_content': ''
        }
        
        # Look for key sections in 10-K
        key_sections = []
        
        # Try to find Business section
        for heading in soup.find_all(['h1', 'h2', 'h3', 'b']):
            heading_text = heading.get_text().upper()
            if 'BUSINESS' in heading_text and 'ITEM' in heading_text:
                # Get next 10k chars
                parent = heading.parent
                if parent:
                    section_text = parent.get_text()[:10000]
                    key_sections.append(section_text)
                    break
        
        # Try to find MD&A section
        for heading in soup.find_all(['h1', 'h2', 'h3', 'b']):
            heading_text = heading.get_text().upper()
            if 'MANAGEMENT' in heading_text and 'DISCUSSION' in heading_text:
                parent = heading.parent
                if parent:
                    section_text = parent.get_text()[:15000]
                    key_sections.append(section_text)
                    break
        
        if key_sections:
            sections['primary_content'] = '\n\n'.join(key_sections)
        else:
            sections['primary_content'] = full_text[:50000]
        
        return sections
    
    def _extract_10q_sections(self, soup: BeautifulSoup, full_text: str) -> Dict[str, str]:
        """Extract sections from 10-Q filing"""
        # Similar to 10-K but focus on quarterly data
        return self._extract_10k_sections(soup, full_text)
    
    def _extract_s1_sections(self, soup: BeautifulSoup, full_text: str) -> Dict[str, str]:
        """Extract sections from S-1 filing"""
        sections = {
            'full_text': full_text,
            'primary_content': ''
        }
        
        # Look for prospectus summary
        for heading in soup.find_all(['h1', 'h2', 'h3']):
            heading_text = heading.get_text().upper()
            if 'PROSPECTUS SUMMARY' in heading_text or 'SUMMARY' in heading_text:
                parent = heading.parent
                if parent:
                    section_text = parent.get_text()[:20000]
                    sections['primary_content'] = section_text
                    break
        
        if not sections['primary_content']:
            sections['primary_content'] = full_text[:50000]
        
        return sections
    
    def _clean_text(self, text: str) -> str:
        """
        Clean extracted text
        """
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters that might interfere with processing
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        
        # Remove repeated underscores or dashes (often used as separators)
        text = re.sub(r'[_\-]{4,}', '', text)
        
        # Trim
        text = text.strip()
        
        return text
    
    def extract_financial_tables(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extract financial tables from HTML
        This is a helper method for future enhancement
        """
        tables = []
        
        # Look for tables with financial keywords
        financial_keywords = ['revenue', 'income', 'assets', 'liabilities', 'cash', 'earnings']
        
        for table in soup.find_all('table'):
            table_text = table.get_text().lower()
            if any(keyword in table_text for keyword in financial_keywords):
                # Extract table data
                rows = []
                for tr in table.find_all('tr'):
                    cols = [td.get_text().strip() for td in tr.find_all(['td', 'th'])]
                    if cols:
                        rows.append(cols)
                
                if rows:
                    tables.append({
                        'rows': rows,
                        'text': table.get_text()
                    })
        
        return tables


# Create singleton instance
text_extractor = TextExtractor()
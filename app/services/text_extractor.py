# app/services/text_extractor.py
"""
Text Extractor Service - Enhanced Version with Exhibit 99 Support
Extracts structured text from SEC filing HTML documents
Enhanced for different filing types (10-K, 10-Q, 8-K, S-1)
FIXED: Better document type identification with multiple patterns
FIXED: Smart content extraction based on filing type
FIXED: Improved iXBRL handling with content validation
ENHANCED: Added Exhibit 99 extraction for 8-K filings
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
    """
    
    def __init__(self):
        self.min_section_length = 100  # Minimum characters for a valid section
        self.max_section_length = 50000  # Maximum characters to avoid memory issues
        
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
            ]
        }
        
        # Key sections for each filing type
        self.key_sections = {
            '10-K': {
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
                'Summary': {'pattern': r'(?:Prospectus\s+)?Summary', 'max_chars': 20000},
                'Risk Factors': {'pattern': r'Risk\s+Factors', 'max_chars': 25000},
                'Business': {'pattern': r'(?:Our\s+)?Business', 'max_chars': 20000},
                'Use of Proceeds': {'pattern': r'Use\s+of\s+Proceeds', 'max_chars': 10000},
            }
        }
    
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
        
        # Extract from main document
        sections = self.extract_from_html(main_doc)
        
        # ENHANCED: Extract Exhibit 99 for 8-K filings
        if sections.get('filing_type') == '8-K':
            exhibit_99_content = self._extract_exhibit_99(filing_dir)
            if exhibit_99_content:
                logger.info(f"Successfully extracted Exhibit 99 content: {len(exhibit_99_content)} chars")
                
                # Append Exhibit 99 content to primary content
                if 'primary_content' in sections:
                    sections['primary_content'] += f"\n\n{'='*50}\nEXHIBIT 99 CONTENT\n{'='*50}\n\n{exhibit_99_content}"
                else:
                    sections['primary_content'] = exhibit_99_content
                
                # Also append to full text
                if 'full_text' in sections:
                    sections['full_text'] += f"\n\n{exhibit_99_content}"
                
                # Store exhibit content separately for reference
                sections['exhibit_99_content'] = exhibit_99_content
        
        return sections
    
    def _extract_exhibit_99(self, filing_dir: Path) -> Optional[str]:
        """
        Extract content from Exhibit 99 files in the filing directory
        
        Args:
            filing_dir: Path to the filing directory
            
        Returns:
            Combined text from all Exhibit 99 files, or None if not found
        """
        exhibit_99_content = []
        
        # Look for Exhibit 99 files with various naming patterns
        # Based on actual data: kmi2025q28-kex991.htm format
        exhibit_patterns = [
            "*ex99*.htm",      # Covers most variants
            "*ex99*.html",
            "*kex99*.htm",     # KMI format: kmi2025q28-kex991.htm
            "*kex99*.html",
            "*dex99*.htm",     # Possible Dominion format
            "*dex99*.html",
            "ex-99*.htm",      # Standard format
            "ex-99*.html",
            "ex99*.htm",
            "ex99*.html",
            "exhibit99*.htm",
            "exhibit99*.html",
            "ex_99*.htm",
            "ex_99*.html"
        ]
        
        exhibit_files = []
        for pattern in exhibit_patterns:
            exhibit_files.extend(filing_dir.glob(pattern))
        
        # Remove duplicates and sort by filename
        exhibit_files = sorted(set(exhibit_files), key=lambda x: x.name)
        
        if not exhibit_files:
            logger.info("No Exhibit 99 files found")
            return None
        
        logger.info(f"Found {len(exhibit_files)} Exhibit 99 file(s): {[f.name for f in exhibit_files]}")
        
        for exhibit_file in exhibit_files:
            try:
                # Check file size - skip if too large (>50MB)
                if exhibit_file.stat().st_size > 50 * 1024 * 1024:
                    logger.warning(f"Skipping {exhibit_file.name} - file too large (>50MB)")
                    continue
                
                # Read and extract content
                with open(exhibit_file, 'r', encoding='utf-8', errors='ignore') as f:
                    html_content = f.read()
                
                # Parse with BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Remove script and style elements
                for element in soup(['script', 'style', 'link', 'meta']):
                    element.decompose()
                
                # Extract text
                text = soup.get_text()
                
                # Clean up text
                text = self._clean_text(text)
                
                # Add header for this exhibit
                if text and len(text) > 100:  # Only include if substantial content
                    header = f"\n{'='*40}\nExhibit 99: {exhibit_file.name}\n{'='*40}\n"
                    exhibit_99_content.append(header + text)
                    logger.info(f"Extracted {len(text)} chars from {exhibit_file.name}")
                
            except Exception as e:
                logger.error(f"Error extracting from {exhibit_file.name}: {e}")
                continue
        
        if exhibit_99_content:
            # Combine all exhibit content
            combined_content = '\n\n'.join(exhibit_99_content)
            
            # Limit total size to avoid overwhelming the AI
            max_exhibit_chars = 100000  # 100K chars max for exhibits
            if len(combined_content) > max_exhibit_chars:
                logger.warning(f"Exhibit 99 content truncated from {len(combined_content)} to {max_exhibit_chars} chars")
                combined_content = combined_content[:max_exhibit_chars] + "\n\n[Exhibit content truncated...]"
            
            return combined_content
        
        return None
    
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
            
            # Always include full text and primary content
            sections['full_text'] = main_content
            sections['filing_type'] = filing_type
            
            # Ensure we have quality primary content
            if 'primary_content' not in sections or len(sections.get('primary_content', '')) < 1000:
                sections['primary_content'] = self._extract_smart_content(main_content, filing_type)
            
            return sections
            
        except Exception as e:
            logger.error(f"Error extracting from TXT file {txt_path}: {e}")
            return {'error': str(e)}
    
    def extract_from_html(self, html_path: Path) -> Dict[str, str]:
        """
        Extract structured text sections from an HTML filing
        
        Args:
            html_path: Path to the HTML file
            
        Returns:
            Dictionary with keys: 'full_text', 'primary_content', 'filing_type'
        """
        try:
            with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            
            # Identify filing type from raw HTML first
            filing_type = self._identify_filing_type_enhanced(html_content)
            logger.info(f"Initial document type identified from HTML: {filing_type}")
            
            # Check if this is an iXBRL document
            if 'ix:' in html_content or 'inline XBRL' in html_content.lower():
                logger.info("Detected iXBRL document, using special extraction")
                return self._extract_from_ixbrl(html_content, filing_type)
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
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
            
            # Always ensure we have these keys
            sections['full_text'] = text
            sections['filing_type'] = filing_type
            
            # Ensure quality primary content
            if 'primary_content' not in sections or len(sections.get('primary_content', '')) < 1000:
                sections['primary_content'] = self._extract_smart_content(text, filing_type)
            
            return sections
            
        except Exception as e:
            logger.error(f"Error extracting text from {html_path}: {e}")
            return {'error': str(e)}
    
    def _identify_filing_type_enhanced(self, text: str) -> str:
        """
        Enhanced filing type identification using multiple patterns and scoring
        """
        # Expand search range to catch more patterns
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
        if filing_type == '8-K':
            return self._extract_8k_sections_enhanced(text)
        elif filing_type == '10-K':
            return self._extract_10k_sections_enhanced(text)
        elif filing_type == '10-Q':
            return self._extract_10q_sections_enhanced(text)
        elif filing_type == 'S-1':
            return self._extract_s1_sections_enhanced(text)
        else:
            return {'primary_content': text[:50000]}
    
    def _extract_smart_content(self, text: str, filing_type: str) -> str:
        """
        Smart content extraction when standard methods fail
        """
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
        
        for para in paragraphs:
            if len(para) < 100:  # Skip short paragraphs
                continue
                
            score = 0
            para_lower = para.lower()
            
            # Score based on keyword presence
            for keyword in value_keywords:
                score += para_lower.count(keyword)
            
            # Bonus for financial numbers
            score += len(re.findall(r'\$[\d,]+', para)) * 2
            score += len(re.findall(r'\d+\.\d+%', para)) * 2
            
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
            r'Item\s+(\d+\.\d+)',
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
        Enhanced S-1 extraction for IPO documents
        """
        sections = {}
        combined_content = []
        
        # Extract each key section
        for section_name, section_info in self.key_sections['S-1'].items():
            pattern = section_info['pattern']
            max_chars = section_info['max_chars']
            
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start = match.start()
                end = min(start + max_chars, len(text))
                
                section_text = text[start:end]
                
                if len(section_text) > 500:
                    header = f"\n{'='*50}\n{section_name}\n{'='*50}\n"
                    combined_content.append(header + section_text)
                    logger.info(f"Extracted {section_name} from S-1: {len(section_text)} chars")
        
        if combined_content:
            sections['primary_content'] = '\n\n'.join(combined_content)
        
        # Look for offering details
        offering_match = re.search(r'The\s+Offering|Offering\s+Summary', text, re.IGNORECASE)
        if offering_match:
            offering_start = offering_match.start()
            offering_section = text[offering_start:offering_start + 5000]
            sections['offering_details'] = offering_section
        
        return sections
    
    def _extract_from_ixbrl(self, html_content: str, pre_identified_type: str = None) -> Dict[str, str]:
        """
        Enhanced iXBRL extraction with better content preservation
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove all ix: namespace elements' tags but keep their text
        for elem in soup.find_all(re.compile(r'^ix:', re.I)):
            elem.unwrap()
        
        # Remove script and style
        for element in soup(['script', 'style', 'link', 'meta', 'noscript']):
            element.decompose()
        
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
        sections['filing_type'] = filing_type
        
        # Ensure primary content
        if 'primary_content' not in sections or len(sections.get('primary_content', '')) < 1000:
            sections['primary_content'] = self._extract_smart_content(text, filing_type)
        
        return sections
    
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
        Extract financial tables from HTML
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
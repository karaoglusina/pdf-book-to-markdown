"""Split PDF content based on TOC structure."""

import re
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from .toc_parser import TOCParser, TOCItem
from .pdf_parser import PDFParser, TextBlock, ImageBlock, Footnote


@dataclass
class SectionContent:
    """Content for a specific section."""
    section: TOCItem
    intro_text: str  # Text before first subsection
    full_text: str  # All text including subsections
    page_start: int
    page_end: int
    confidence: float  # 0-1, how confident we are in the split
    images: List[ImageBlock] = field(default_factory=list)
    footnotes: List[Footnote] = field(default_factory=list)
    subsection_texts: Dict[str, str] = field(default_factory=dict)  # subsection_number -> text


class ContentSplitter:
    """Match PDF content with TOC structure and split accordingly."""
    
    def __init__(self, toc_parser: TOCParser, pdf_parser: PDFParser):
        self.toc_parser = toc_parser
        self.pdf_parser = pdf_parser
        self.logger = logging.getLogger(__name__)
        
        self.section_contents: Dict[str, SectionContent] = {}  # section_number -> content
        
    def split_content(self) -> Dict[str, SectionContent]:
        """Split PDF content according to TOC structure."""
        self.logger.info("Splitting content by sections")
        
        # Get all sections from TOC
        all_sections = self.toc_parser.get_all_sections()
        
        # Detect headers in PDF
        headers = self.pdf_parser.detect_headers()
        
        # Match TOC sections with PDF headers
        section_matches = self._match_sections_to_headers(all_sections, headers)
        
        # Extract content for each section
        for section in all_sections:
            content = self._extract_section_content(section, section_matches, headers)
            if content:
                self.section_contents[section.number] = content
        
        self.logger.info(f"Split content into {len(self.section_contents)} sections")
        return self.section_contents
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        # Remove extra whitespace, punctuation, lowercase
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s]', '', text)
        return text.lower().strip()
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple similarity between two texts."""
        norm1 = self._normalize_text(text1)
        norm2 = self._normalize_text(text2)
        
        if not norm1 or not norm2:
            return 0.0
        
        # Simple word overlap
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union) if union else 0.0
    
    def _match_sections_to_headers(self, sections: List[TOCItem], 
                                   headers: List[Dict]) -> Dict[str, Dict]:
        """Match TOC sections to PDF headers."""
        matches = {}
        
        for section in sections:
            best_match = None
            best_score = 0.0
            
            # Try to match section title with headers
            for i, header in enumerate(headers):
                # Calculate similarity
                similarity = self._calculate_similarity(section.title, header['text'])
                
                # Bonus for level match
                if header['level'] == section.level:
                    similarity += 0.2
                
                # Bonus for number match
                if section.number in header['text']:
                    similarity += 0.3
                
                if similarity > best_score:
                    best_score = similarity
                    best_match = {
                        'header': header,
                        'header_index': i,
                        'score': similarity
                    }
            
            if best_match and best_match['score'] > 0.3:  # Threshold
                matches[section.number] = best_match
                self.logger.debug(f"Matched section {section.number} '{section.title}' "
                                f"to header '{best_match['header']['text']}' "
                                f"(score: {best_match['score']:.2f})")
            else:
                self.logger.warning(f"Could not confidently match section {section.number} "
                                  f"'{section.title}'")
        
        return matches
    
    def _extract_section_content(self, section: TOCItem, 
                                 matches: Dict[str, Dict],
                                 headers: List[Dict]) -> Optional[SectionContent]:
        """Extract content for a specific section."""
        
        # Check if we have a match for this section
        if section.number not in matches:
            self.logger.warning(f"No match found for section {section.number}, using fallback")
            return self._extract_by_fallback(section)
        
        match = matches[section.number]
        header_idx = match['header_index']
        current_header = match['header']
        
        # Find the next header at same or higher level to determine end
        page_start = current_header['page']
        page_end = None
        
        for next_header in headers[header_idx + 1:]:
            if next_header['level'] <= current_header['level']:
                page_end = next_header['page']
                break
        
        if page_end is None:
            # This is the last section, go to end of document
            page_end = max(block.page_num for block in self.pdf_parser.blocks) if self.pdf_parser.blocks else page_start
        
        # Ensure page_end is at least page_start
        if page_end < page_start:
            page_end = page_start
        
        # Extract all text between start and end pages
        full_text = self._extract_text_between_pages(page_start, page_end)
        
        # Extract subsection content
        subsection_texts = self._extract_subsection_texts(section, full_text, headers, page_start, page_end)
        
        # Extract intro text (before first subsection)
        intro_text = self._extract_intro_text(section, full_text, page_start, page_end)
        
        # Get images for this section
        images = self.pdf_parser.get_images_for_pages(page_start, page_end)
        
        # Get footnotes for this section
        footnotes = self.pdf_parser.get_footnotes_for_pages(page_start, page_end)
        
        return SectionContent(
            section=section,
            intro_text=intro_text,
            full_text=full_text,
            page_start=page_start,
            page_end=page_end,
            confidence=match['score'],
            images=images,
            footnotes=footnotes,
            subsection_texts=subsection_texts
        )
    
    def _extract_subsection_texts(self, section: TOCItem, full_text: str,
                                  headers: List[Dict], page_start: int, 
                                  page_end: int) -> Dict[str, str]:
        """Extract text for each subsection."""
        subsection_texts = {}
        
        if not section.children:
            return subsection_texts
        
        # Find subsection headers in the full text
        for i, subsection in enumerate(section.children):
            # Try to find this subsection's content
            start_pattern = self._create_header_pattern(subsection.title, subsection.number)
            
            # Find next subsection or end of section
            if i < len(section.children) - 1:
                next_subsection = section.children[i + 1]
                end_pattern = self._create_header_pattern(next_subsection.title, next_subsection.number)
            else:
                end_pattern = None
            
            # Extract text between patterns
            start_match = re.search(start_pattern, full_text, re.IGNORECASE | re.MULTILINE)
            
            if start_match:
                text_start = start_match.end()
                
                if end_pattern:
                    end_match = re.search(end_pattern, full_text[text_start:], re.IGNORECASE | re.MULTILINE)
                    if end_match:
                        subsection_text = full_text[text_start:text_start + end_match.start()]
                    else:
                        # Take remaining text
                        subsection_text = full_text[text_start:]
                else:
                    # Last subsection, take remaining text
                    subsection_text = full_text[text_start:]
                
                subsection_texts[subsection.number] = subsection_text.strip()
        
        return subsection_texts
    
    def _create_header_pattern(self, title: str, number: str) -> str:
        """Create a regex pattern to find a header in text."""
        # Escape special regex characters in title
        escaped_title = re.escape(title)
        # Allow some flexibility in matching
        escaped_title = escaped_title.replace(r'\ ', r'\s+')
        
        # Match either the number or the title
        patterns = [
            rf'{re.escape(number)}[\.\s]+{escaped_title}',  # "1.1.1 Title"
            rf'{escaped_title}',  # Just the title
        ]
        
        return '|'.join(f'({p})' for p in patterns)
    
    def _extract_by_fallback(self, section: TOCItem) -> Optional[SectionContent]:
        """Fallback content extraction by searching for section title in text."""
        # Search through all blocks for the section title
        for i, block in enumerate(self.pdf_parser.blocks):
            similarity = self._calculate_similarity(section.title, block.text)
            if similarity > 0.5 or section.number in block.text:
                # Found potential match
                page_start = block.page_num
                # Assume section is about 10 pages or until we find next section
                page_end = min(page_start + 10, 
                             max(b.page_num for b in self.pdf_parser.blocks) if self.pdf_parser.blocks else page_start)
                
                full_text = self._extract_text_between_pages(page_start, page_end)
                images = self.pdf_parser.get_images_for_pages(page_start, page_end)
                footnotes = self.pdf_parser.get_footnotes_for_pages(page_start, page_end)
                
                return SectionContent(
                    section=section,
                    intro_text=full_text[:1000],  # First 1000 chars as intro
                    full_text=full_text,
                    page_start=page_start,
                    page_end=page_end,
                    confidence=0.3,  # Low confidence
                    images=images,
                    footnotes=footnotes
                )
        
        return None
    
    def _extract_text_between_pages(self, start_page: int, end_page: int) -> str:
        """Extract and clean text between pages."""
        text_parts = []
        
        for block in self.pdf_parser.blocks:
            if start_page <= block.page_num <= end_page:
                text_parts.append(block.text)
        
        # Join text with proper paragraph spacing
        full_text = self._join_paragraphs(text_parts)
        
        # Clean up common PDF artifacts
        full_text = self._clean_text(full_text)
        
        return full_text
    
    def _join_paragraphs(self, text_parts: List[str]) -> str:
        """Join text parts into paragraphs intelligently."""
        if not text_parts:
            return ""
        
        result_parts = []
        current_paragraph = []
        
        for text in text_parts:
            text = text.strip()
            if not text:
                continue
            
            # Check if this looks like a new paragraph
            is_new_paragraph = (
                # Starts with uppercase after a complete sentence
                (current_paragraph and 
                 current_paragraph[-1].rstrip().endswith(('.', '!', '?', ':')) and
                 text[0].isupper()) or
                # Is a header
                re.match(r'^[\d\.]+\s+[A-Z]', text) or
                # Is a list item
                re.match(r'^[\-\*\•\d]+[\.\)]\s', text) or
                # Has significant indentation (code block indicator)
                text.startswith('    ')
            )
            
            if is_new_paragraph and current_paragraph:
                result_parts.append(' '.join(current_paragraph))
                current_paragraph = []
            
            current_paragraph.append(text)
        
        if current_paragraph:
            result_parts.append(' '.join(current_paragraph))
        
        return '\n\n'.join(result_parts)
    
    def _clean_text(self, text: str) -> str:
        """Clean up extracted text."""
        # Fix common hyphenation issues
        text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
        
        # Normalize whitespace
        text = re.sub(r'\n\n\n+', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        # Remove lone page numbers
        text = re.sub(r'\n\d+\n', '\n', text)
        
        # Fix broken sentences (single letters on their own)
        text = re.sub(r'\n([a-zA-Z])\n', r'\1', text)
        
        return text.strip()
    
    def _extract_intro_text(self, section: TOCItem, full_text: str,
                           page_start: int, page_end: int) -> str:
        """Extract intro text before first subsection."""
        
        if not section.children:
            # No subsections, entire text is intro
            return full_text
        
        # Find first subsection title in text
        for subsection in section.children:
            # Try to find subsection title in text
            pattern = self._create_header_pattern(subsection.title, subsection.number)
            match = re.search(pattern, full_text, re.IGNORECASE)
            
            if match:
                # Return text before this point
                intro = full_text[:match.start()].strip()
                if len(intro) > 50:  # Reasonable amount of text
                    return intro
        
        # Fallback: return first 30% of text as intro
        split_point = len(full_text) // 3
        return full_text[:split_point].strip()
    
    def get_chapter_intro(self, chapter: TOCItem) -> str:
        """Get intro text for a chapter (before first section)."""
        if not chapter.children:
            return ""
        
        first_section = chapter.children[0]
        if first_section.number not in self.section_contents:
            return ""
        
        first_section_content = self.section_contents[first_section.number]
        
        # Text before first section is chapter intro
        # We need to look at blocks before first section's page
        chapter_start = first_section_content.page_start - 5  # Look back a few pages
        chapter_end = first_section_content.page_start - 1
        
        if chapter_start < 1:
            chapter_start = 1
        
        if chapter_end < chapter_start:
            return ""
        
        return self._extract_text_between_pages(chapter_start, chapter_end)


if __name__ == "__main__":
    # Test
    import sys
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 2:
        toc_parser = TOCParser(sys.argv[1])
        toc_parser.parse()
        
        pdf_parser = PDFParser(sys.argv[2])
        pdf_parser.extract_blocks()
        
        splitter = ContentSplitter(toc_parser, pdf_parser)
        contents = splitter.split_content()
        
        print(f"\nExtracted content for {len(contents)} sections")
        for num, content in list(contents.items())[:3]:
            print(f"\nSection {num}: {content.section.title}")
            print(f"  Pages: {content.page_start}-{content.page_end}")
            print(f"  Confidence: {content.confidence:.2f}")
            print(f"  Intro length: {len(content.intro_text)} chars")
            print(f"  Full length: {len(content.full_text)} chars")
            print(f"  Images: {len(content.images)}")
            print(f"  Footnotes: {len(content.footnotes)}")

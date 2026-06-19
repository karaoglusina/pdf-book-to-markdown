"""Extract text, images, and structure from PDF files."""

import fitz  # PyMuPDF
import pdfplumber
import re
import os
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
import logging
from pathlib import Path


@dataclass
class TextBlock:
    """Represents a block of text with styling information."""
    text: str
    page_num: int
    font_size: float
    font_name: str
    is_bold: bool
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1
    block_type: str = "body"  # body, header, footer, footnote, caption
    
    def __repr__(self):
        return f"TextBlock(page={self.page_num}, font={self.font_size:.1f}, type={self.block_type}, text={self.text[:50]}...)"


@dataclass
class ImageBlock:
    """Represents an image extracted from the PDF."""
    page_num: int
    bbox: Tuple[float, float, float, float]
    image_path: str  # Path where image is saved
    caption: Optional[str] = None
    width: int = 0
    height: int = 0
    y_position: float = 0  # Vertical position on page for ordering
    
    @property
    def filename(self) -> str:
        """Get just the filename without path."""
        return Path(self.image_path).name
    
    def __repr__(self):
        return f"ImageBlock(page={self.page_num}, y={self.y_position:.0f}, path={self.filename})"


@dataclass 
class Footnote:
    """Represents a footnote."""
    number: str
    text: str
    page_num: int
    
    def __repr__(self):
        return f"Footnote({self.number}: {self.text[:30]}...)"


@dataclass
class PDFSection:
    """Represents a detected section in the PDF."""
    title: str
    level: int  # 1=chapter, 2=section, 3=subsection
    page_start: int
    page_end: Optional[int] = None
    blocks: List[TextBlock] = None
    
    def __post_init__(self):
        if self.blocks is None:
            self.blocks = []


@dataclass
class PageContent:
    """Content for a single page."""
    page_num: int
    blocks: List[TextBlock] = field(default_factory=list)
    images: List[ImageBlock] = field(default_factory=list)
    footnotes: List[Footnote] = field(default_factory=list)
    header_text: str = ""
    footer_text: str = ""


class PDFParser:
    """Extract structured content from PDF files."""
    
    def __init__(self, pdf_path: str, config: Dict = None, output_dir: str = None):
        self.pdf_path = pdf_path
        self.config = config or {}
        self.output_dir = output_dir
        self.logger = logging.getLogger(__name__)
        
        # Font size thresholds for header detection
        self.chapter_min_size = self.config.get('min_font_size_chapter', 16.0)
        self.section_min_size = self.config.get('min_font_size_section', 14.0)
        
        # Content storage
        self.blocks: List[TextBlock] = []
        self.images: List[ImageBlock] = []
        self.footnotes: List[Footnote] = []
        self.page_contents: Dict[int, PageContent] = {}
        self.sections: List[PDFSection] = []
        
        # Page layout info
        self.page_heights: Dict[int, float] = {}
        self.page_widths: Dict[int, float] = {}
        
        # Header/footer detection
        self.detected_headers: Set[str] = set()
        self.detected_footers: Set[str] = set()
        
        # Image output directory
        if output_dir:
            self.image_dir = Path(output_dir) / "images"
        else:
            self.image_dir = Path(pdf_path).parent / "images"
        
    def extract_all(self) -> Tuple[List[TextBlock], List[ImageBlock], List[Footnote]]:
        """Extract all content from PDF: text, images, and footnotes."""
        self.logger.info(f"Extracting all content from {self.pdf_path}")
        
        try:
            doc = fitz.open(self.pdf_path)
            
            # First pass: detect repeating headers/footers
            self._detect_repeating_elements(doc)
            
            # Second pass: extract all content
            for page_num in range(len(doc)):
                page = doc[page_num]
                self._extract_page_content(doc, page, page_num + 1)
            
            doc.close()
            
            self.logger.info(f"Extracted {len(self.blocks)} text blocks, "
                           f"{len(self.images)} images, {len(self.footnotes)} footnotes")
            
            return self.blocks, self.images, self.footnotes
            
        except Exception as e:
            self.logger.error(f"Error extracting content: {e}")
            return self._fallback_extraction()
    
    def extract_blocks(self) -> List[TextBlock]:
        """Extract all text blocks (legacy method for compatibility)."""
        blocks, _, _ = self.extract_all()
        return blocks
    
    def _detect_repeating_elements(self, doc):
        """Detect repeating header/footer text across pages."""
        self.logger.info("Detecting repeating headers/footers...")
        
        header_candidates = {}  # text -> count
        footer_candidates = {}
        
        for page_num in range(min(len(doc), 50)):  # Sample first 50 pages
            page = doc[page_num]
            page_height = page.rect.height
            page_width = page.rect.width
            
            self.page_heights[page_num + 1] = page_height
            self.page_widths[page_num + 1] = page_width
            
            blocks_data = page.get_text("dict")["blocks"]
            
            for block in blocks_data:
                if block.get("type") != 0:
                    continue
                    
                # Reconstruct block text
                block_text = ""
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        block_text += span.get("text", "")
                
                block_text = block_text.strip()
                if not block_text or len(block_text) < 3:
                    continue
                
                bbox = block.get("bbox", (0, 0, 0, 0))
                y0, y1 = bbox[1], bbox[3]
                
                # Header zone: top 10% of page
                if y0 < page_height * 0.10:
                    header_candidates[block_text] = header_candidates.get(block_text, 0) + 1
                
                # Footer zone: bottom 10% of page
                if y1 > page_height * 0.90:
                    footer_candidates[block_text] = footer_candidates.get(block_text, 0) + 1
        
        # Elements appearing on more than 30% of sampled pages are likely headers/footers
        threshold = max(3, len(doc) * 0.3)
        
        for text, count in header_candidates.items():
            if count >= threshold:
                self.detected_headers.add(text)
                self.logger.debug(f"Detected header: {text[:50]}...")
        
        for text, count in footer_candidates.items():
            if count >= threshold:
                self.detected_footers.add(text)
                self.logger.debug(f"Detected footer: {text[:50]}...")
        
        self.logger.info(f"Detected {len(self.detected_headers)} repeating headers, "
                        f"{len(self.detected_footers)} repeating footers")
    
    def _extract_page_content(self, doc, page, page_num: int):
        """Extract all content from a single page."""
        page_height = page.rect.height
        page_width = page.rect.width
        
        self.page_heights[page_num] = page_height
        self.page_widths[page_num] = page_width
        
        page_content = PageContent(page_num=page_num)
        
        # Get text blocks with structure preserved
        blocks_data = page.get_text("dict")["blocks"]
        
        # Extract images first
        self._extract_images_from_page(doc, page, page_num, page_content)
        
        # Process text blocks
        for block in blocks_data:
            if block.get("type") == 0:  # Text block
                self._process_text_block(
                    block, page_num, page_height, page_width, page_content
                )
        
        # Store page content
        self.page_contents[page_num] = page_content
    
    def _process_text_block(self, block, page_num: int, page_height: float, 
                           page_width: float, page_content: PageContent):
        """Process a text block, merging lines intelligently."""
        
        bbox = block.get("bbox", (0, 0, 0, 0))
        y0, y1 = bbox[1], bbox[3]
        x0, x1 = bbox[0], bbox[2]
        
        # Collect all text from this block with proper line merging
        lines_text = []
        block_font_size = 0
        block_font_name = ""
        block_is_bold = False
        
        for line in block.get("lines", []):
            line_text_parts = []
            line_font_size = 0
            
            for span in line.get("spans", []):
                text = span.get("text", "")
                if text:
                    line_text_parts.append(text)
                    line_font_size = max(line_font_size, span.get("size", 0))
                    if not block_font_name:
                        block_font_name = span.get("font", "")
                    if "bold" in span.get("font", "").lower():
                        block_is_bold = True
            
            line_text = "".join(line_text_parts)
            if line_text.strip():
                lines_text.append(line_text)
                block_font_size = max(block_font_size, line_font_size)
        
        if not lines_text:
            return
        
        # Merge lines intelligently
        merged_text = self._merge_lines(lines_text)
        
        if not merged_text.strip():
            return
        
        # Determine block type
        block_type = self._classify_block(
            merged_text, y0, y1, page_height, block_font_size
        )
        
        # Skip headers/footers
        if block_type in ("header", "footer"):
            if block_type == "header":
                page_content.header_text = merged_text
            else:
                page_content.footer_text = merged_text
            return
        
        # Handle footnotes
        if block_type == "footnote":
            footnote = self._parse_footnote(merged_text, page_num)
            if footnote:
                self.footnotes.append(footnote)
                page_content.footnotes.append(footnote)
            return
        
        # Create text block
        text_block = TextBlock(
            text=merged_text,
            page_num=page_num,
            font_size=block_font_size,
            font_name=block_font_name,
            is_bold=block_is_bold,
            bbox=bbox,
            block_type=block_type
        )
        
        self.blocks.append(text_block)
        page_content.blocks.append(text_block)
    
    def _merge_lines(self, lines: List[str]) -> str:
        """Merge lines intelligently, handling hyphenation and line breaks."""
        if not lines:
            return ""
        
        merged_parts = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Handle hyphenation at end of line
            if line.endswith('-') and i < len(lines) - 1:
                # Remove hyphen and merge with next line
                line = line[:-1]
                merged_parts.append(line)
            else:
                # Check if this line should be joined with previous
                if merged_parts:
                    prev = merged_parts[-1]
                    # Don't add space if previous ends with certain chars
                    if prev.endswith(('-', '/', '(')):
                        merged_parts.append(line)
                    # Don't add space if current starts with certain chars  
                    elif line.startswith((')', ',', '.', ';', ':')):
                        merged_parts.append(line)
                    else:
                        merged_parts.append(' ' + line)
                else:
                    merged_parts.append(line)
        
        result = ''.join(merged_parts)
        
        # Clean up multiple spaces
        result = re.sub(r' +', ' ', result)
        
        return result.strip()
    
    def _classify_block(self, text: str, y0: float, y1: float, 
                       page_height: float, font_size: float) -> str:
        """Classify a block as header, footer, footnote, or body text."""
        
        text_clean = text.strip()
        
        # Check against detected repeating headers/footers
        for header in self.detected_headers:
            if text_clean == header or header in text_clean:
                return "header"
        
        for footer in self.detected_footers:
            if text_clean == footer or footer in text_clean:
                return "footer"
        
        # Check position
        header_zone = page_height * 0.08
        footer_zone = page_height * 0.92
        
        # Header zone checks
        if y0 < header_zone:
            # Check for page number patterns
            if re.match(r'^\d+$', text_clean):
                return "header"
            # Check for chapter/section title patterns at top
            if re.match(r'^(Chapter|Part|Section)\s+\d+', text_clean, re.IGNORECASE):
                return "header"
            # Check for repeating section names with pipe
            if '|' in text_clean and len(text_clean) < 100:
                return "header"
        
        # Footer zone checks
        if y1 > footer_zone:
            # Page numbers
            if re.match(r'^\d+$', text_clean):
                return "footer"
            # Chapter/section title at bottom
            if re.match(r'^(Chapter|Part|Section)\s+\d+', text_clean, re.IGNORECASE):
                return "footer"
            # Page info patterns
            if re.search(r'(page|pg\.?)\s*\d+', text_clean, re.IGNORECASE):
                return "footer"
            # Repeating titles with pipe
            if '|' in text_clean and len(text_clean) < 100:
                return "footer"
        
        # Footnote detection: small font at bottom, starts with number
        if y1 > page_height * 0.85 and font_size < 9:
            if re.match(r'^[\d†‡§¶\*]+\s', text_clean):
                return "footnote"
        
        return "body"
    
    def _parse_footnote(self, text: str, page_num: int) -> Optional[Footnote]:
        """Parse footnote text into a Footnote object."""
        # Match common footnote patterns
        match = re.match(r'^([\d†‡§¶\*]+)\s+(.+)$', text.strip())
        if match:
            return Footnote(
                number=match.group(1),
                text=match.group(2),
                page_num=page_num
            )
        return None
    
    def _extract_images_from_page(self, doc, page, page_num: int, 
                                  page_content: PageContent):
        """Extract and save images from a page with position information."""
        # Create image directory if needed
        self.image_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Get image positions using page.get_image_info()
            image_info_list = page.get_image_info(xrefs=True)
            img_list = page.get_images(full=True)
            
            # Create a mapping of xref to position
            xref_to_bbox = {}
            for info in image_info_list:
                xref = info.get('xref', 0)
                bbox = info.get('bbox', (0, 0, 0, 0))
                if xref and bbox:
                    xref_to_bbox[xref] = bbox
            
            for img_idx, img_info in enumerate(img_list):
                xref = img_info[0]
                
                try:
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # Generate unique filename
                    image_filename = f"page{page_num}_img{img_idx + 1}.{image_ext}"
                    image_path = self.image_dir / image_filename
                    
                    # Save image
                    with open(image_path, "wb") as f:
                        f.write(image_bytes)
                    
                    # Get image position on page
                    bbox = xref_to_bbox.get(xref, (0, 0, base_image.get("width", 0), base_image.get("height", 0)))
                    y_position = bbox[1] if len(bbox) >= 2 else 0  # y0 position
                    
                    image_block = ImageBlock(
                        page_num=page_num,
                        bbox=bbox,
                        image_path=str(image_path),
                        caption=None,  # Will be set by _find_image_captions
                        width=base_image.get("width", 0),
                        height=base_image.get("height", 0),
                        y_position=y_position
                    )
                    
                    self.images.append(image_block)
                    page_content.images.append(image_block)
                    
                    self.logger.debug(f"Extracted image: {image_path} at y={y_position}")
                    
                except Exception as e:
                    self.logger.warning(f"Could not extract image {xref}: {e}")
            
            # Find captions for images on this page
            self._find_image_captions(page_num, page_content)
                    
        except Exception as e:
            self.logger.warning(f"Error processing images on page {page_num}: {e}")
    
    def _find_image_captions(self, page_num: int, page_content: PageContent):
        """Find and associate captions with images on a page."""
        caption_pattern = re.compile(r'^(Figure|Fig\.|Table|Image|Illustration)\s+[\d\-\.]+', re.IGNORECASE)
        
        for image in page_content.images:
            image_bottom = image.bbox[3] if len(image.bbox) >= 4 else image.y_position + 100
            
            best_caption = None
            best_distance = float('inf')
            
            # Look for caption text below the image
            for block in page_content.blocks:
                block_top = block.bbox[1] if len(block.bbox) >= 2 else 0
                
                # Caption should be below image and close to it
                if block_top >= image_bottom - 20:  # Allow some overlap
                    distance = block_top - image_bottom
                    
                    # Check if this looks like a caption
                    if caption_pattern.match(block.text.strip()):
                        if distance < best_distance and distance < 100:  # Within 100 units
                            best_caption = block.text.strip()
                            best_distance = distance
            
            if best_caption:
                image.caption = best_caption
                self.logger.debug(f"Found caption for image: {best_caption[:50]}...")
    
    def detect_headers(self) -> List[Dict]:
        """Detect headers based on font size and formatting."""
        self.logger.info("Detecting headers")
        headers = []
        
        # Analyze font sizes to determine thresholds dynamically
        font_sizes = [block.font_size for block in self.blocks if block.font_size > 0]
        if font_sizes:
            avg_size = sum(font_sizes) / len(font_sizes)
            self.logger.info(f"Average font size: {avg_size:.2f}")
        
        for block in self.blocks:
            if block.block_type not in ("body",):
                continue
                
            is_header = False
            level = 0
            
            # Pattern matching for chapter/section numbers
            chapter_pattern = r'^(Chapter\s+)?\d+[\.\s]+'
            section_pattern = r'^\d+\.\d+[\.\s]+'
            subsection_pattern = r'^\d+\.\d+\.\d+[\.\s]+'
            
            if block.font_size >= self.chapter_min_size or re.match(chapter_pattern, block.text, re.IGNORECASE):
                is_header = True
                level = 1
            elif block.font_size >= self.section_min_size or re.match(section_pattern, block.text):
                is_header = True
                level = 2
            elif re.match(subsection_pattern, block.text):
                is_header = True
                level = 3
            
            # Additional heuristics: short text, bold, ends without punctuation
            if block.is_bold and len(block.text) < 100 and not block.text.endswith('.'):
                if level == 0:
                    level = 2  # Default to section level
                is_header = True
            
            if is_header:
                headers.append({
                    'text': block.text,
                    'level': level,
                    'page': block.page_num,
                    'font_size': block.font_size,
                    'block': block
                })
        
        self.logger.info(f"Detected {len(headers)} potential headers")
        return headers
    
    def get_text_between_pages(self, start_page: int, end_page: int) -> str:
        """Get all text between two pages."""
        text_parts = []
        
        for block in self.blocks:
            if start_page <= block.page_num <= end_page:
                text_parts.append(block.text)
        
        return '\n'.join(text_parts)
    
    def get_images_for_pages(self, start_page: int, end_page: int) -> List[ImageBlock]:
        """Get all images between two pages."""
        return [img for img in self.images 
                if start_page <= img.page_num <= end_page]
    
    def get_footnotes_for_pages(self, start_page: int, end_page: int) -> List[Footnote]:
        """Get all footnotes between two pages."""
        return [fn for fn in self.footnotes 
                if start_page <= fn.page_num <= end_page]
    
    def get_font_size_stats(self) -> Dict:
        """Get statistics about font sizes in the document."""
        font_sizes = [block.font_size for block in self.blocks if block.font_size > 0]
        
        if not font_sizes:
            return {}
        
        font_sizes_sorted = sorted(font_sizes, reverse=True)
        
        return {
            'max': max(font_sizes),
            'min': min(font_sizes),
            'avg': sum(font_sizes) / len(font_sizes),
            'top_10_percent': font_sizes_sorted[:len(font_sizes_sorted)//10] if font_sizes_sorted else [],
            'median': sorted(font_sizes)[len(font_sizes)//2]
        }
    
    def extract_text_by_page(self) -> Dict[int, str]:
        """Extract text organized by page number."""
        page_texts = {}
        
        for block in self.blocks:
            if block.page_num not in page_texts:
                page_texts[block.page_num] = []
            page_texts[block.page_num].append(block.text)
        
        return {page: '\n'.join(texts) for page, texts in page_texts.items()}


if __name__ == "__main__":
    # Test the parser
    import sys
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1:
        parser = PDFParser(sys.argv[1])
        blocks, images, footnotes = parser.extract_all()
        
        print(f"\nExtracted {len(blocks)} blocks, {len(images)} images, {len(footnotes)} footnotes")
        
        stats = parser.get_font_size_stats()
        print(f"\nFont size stats: {stats}")
        
        headers = parser.detect_headers()
        print(f"\nDetected headers:")
        for header in headers[:20]:
            print(f"  Level {header['level']}: {header['text'][:80]}")
        
        print(f"\nFootnotes:")
        for fn in footnotes[:10]:
            print(f"  {fn.number}: {fn.text[:60]}...")

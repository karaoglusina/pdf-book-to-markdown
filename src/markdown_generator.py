"""Generate markdown files from extracted content."""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import logging

from .toc_parser import TOCParser, TOCItem
from .content_splitter import ContentSplitter, SectionContent
from .pdf_parser import ImageBlock, Footnote


class MarkdownGenerator:
    """Generate organized markdown files from split content."""
    
    def __init__(self, output_dir: str, toc_parser: TOCParser, 
                 content_splitter: ContentSplitter, config: Dict = None):
        self.output_dir = Path(output_dir)
        self.toc_parser = toc_parser
        self.content_splitter = content_splitter
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        self.add_frontmatter = self.config.get('add_frontmatter', True)
        self.include_intro_files = self.config.get('include_intro_files', True)
        
        # Track created files for TOC linking
        self.created_files: Dict[str, str] = {}  # section_number -> relative_path
        
    def generate_all(self) -> Dict[str, str]:
        """Generate all markdown files."""
        self.logger.info(f"Generating markdown files in {self.output_dir}")
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate files for each chapter
        for chapter in self.toc_parser.items:
            self._generate_chapter(chapter)
        
        self.logger.info(f"Generated {len(self.created_files)} markdown files")
        return self.created_files
    
    def _generate_chapter(self, chapter: TOCItem):
        """Generate files for a chapter."""
        # Create chapter folder
        chapter_folder = self._create_chapter_folder(chapter)
        
        # Generate chapter intro file if requested
        if self.include_intro_files:
            self._generate_chapter_intro(chapter, chapter_folder)
        
        # Generate section files
        for section in chapter.children:
            self._generate_section(section, chapter_folder, chapter)
    
    def _create_chapter_folder(self, chapter: TOCItem) -> Path:
        """Create folder for chapter."""
        # Sanitize folder name
        folder_name = f"{chapter.number.zfill(2)}. {self._sanitize_filename(chapter.title)}"
        folder_path = self.output_dir / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Created chapter folder: {folder_path}")
        return folder_path
    
    def _generate_chapter_intro(self, chapter: TOCItem, chapter_folder: Path):
        """Generate intro file for chapter."""
        intro_text = self.content_splitter.get_chapter_intro(chapter)
        
        if not intro_text or len(intro_text) < 50:
            self.logger.warning(f"No substantial intro found for chapter {chapter.number}")
            return
        
        # Create intro file with chapter folder name (instead of _intro.md)
        folder_name = chapter_folder.name
        intro_file = chapter_folder / f"{folder_name}.md"
        
        content = self._format_markdown_content(
            title=chapter.title,
            section_number=chapter.number,
            body=intro_text,
            is_intro=True
        )
        
        with open(intro_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        relative_path = str(intro_file.relative_to(self.output_dir))
        self.created_files[f"{chapter.number}_intro"] = relative_path
        self.logger.info(f"Created chapter intro: {intro_file}")
    
    def _generate_section(self, section: TOCItem, chapter_folder: Path, chapter: TOCItem):
        """Generate markdown file for a section."""
        # Get section content
        section_content = self.content_splitter.section_contents.get(section.number)
        
        if not section_content:
            self.logger.warning(f"No content found for section {section.number}: {section.title}")
            return
        
        # Create section file
        filename = f"{section.number} {self._sanitize_filename(section.title)}.md"
        file_path = chapter_folder / filename
        
        # Format content with all components
        content = self._format_section_content(section, section_content, chapter)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        relative_path = str(file_path.relative_to(self.output_dir))
        self.created_files[section.number] = relative_path
        self.logger.info(f"Created section file: {file_path}")
    
    def _format_section_content(self, section: TOCItem, content: SectionContent,
                                chapter: TOCItem) -> str:
        """Format complete section content with subsections, images, and footnotes."""
        parts = []
        
        # Add frontmatter if configured
        if self.add_frontmatter:
            parts.append(self._generate_frontmatter(section.title, section.number, chapter.title))
        
        # Add main title
        parts.append(f"# {section.number} {section.title}\n")
        
        # Format and add body with subsections and inline images
        body = self._format_body_with_subsections(section, content)
        
        # Insert images inline near their captions
        body = self._insert_images_inline(body, content.images)
        parts.append(body)
        
        # Add footnotes at the end
        if content.footnotes:
            parts.append(self._format_footnotes(content.footnotes))
        
        return '\n\n'.join(filter(None, parts))
    
    def _format_body_with_subsections(self, section: TOCItem, content: SectionContent) -> str:
        """Format body text with proper subsection headings."""
        
        if not section.children:
            # No subsections, just return cleaned body
            return self._clean_body_text(content.full_text)
        
        # Start with intro text
        result_parts = []
        
        if content.intro_text:
            result_parts.append(self._clean_body_text(content.intro_text))
        
        # Add each subsection with proper heading
        for subsection in section.children:
            subsection_text = content.subsection_texts.get(subsection.number, "")
            
            if subsection_text:
                # Add subsection heading (### for subsection under section)
                heading_level = "##" if subsection.level == 3 else "###"
                result_parts.append(f"{heading_level} {subsection.title}")
                result_parts.append(self._clean_body_text(subsection_text))
            else:
                # Try to find subsection content in full text
                subsection_content = self._extract_subsection_from_full_text(
                    subsection, content.full_text, section.children
                )
                if subsection_content:
                    heading_level = "##" if subsection.level == 3 else "###"
                    result_parts.append(f"{heading_level} {subsection.title}")
                    result_parts.append(self._clean_body_text(subsection_content))
        
        return '\n\n'.join(filter(None, result_parts))
    
    def _extract_subsection_from_full_text(self, subsection: TOCItem, 
                                           full_text: str, 
                                           all_subsections: List[TOCItem]) -> Optional[str]:
        """Try to extract subsection content from full text."""
        # Find this subsection's position in the list
        try:
            idx = all_subsections.index(subsection)
        except ValueError:
            return None
        
        # Create pattern to find subsection title
        title_pattern = self._create_title_pattern(subsection.title)
        match = re.search(title_pattern, full_text, re.IGNORECASE)
        
        if not match:
            return None
        
        start_pos = match.end()
        
        # Find end: next subsection or end of text
        if idx < len(all_subsections) - 1:
            next_subsection = all_subsections[idx + 1]
            next_pattern = self._create_title_pattern(next_subsection.title)
            next_match = re.search(next_pattern, full_text[start_pos:], re.IGNORECASE)
            if next_match:
                end_pos = start_pos + next_match.start()
            else:
                end_pos = len(full_text)
        else:
            end_pos = len(full_text)
        
        return full_text[start_pos:end_pos].strip()
    
    def _create_title_pattern(self, title: str) -> str:
        """Create a flexible regex pattern for matching a title."""
        # Escape special characters
        escaped = re.escape(title)
        # Allow flexible whitespace
        escaped = re.sub(r'\\ ', r'\\s+', escaped)
        return escaped
    
    def _clean_body_text(self, text: str) -> str:
        """Clean and format body text."""
        if not text:
            return ""
        
        text = text.strip()
        
        # Fix broken sentences (isolated single letters)
        text = re.sub(r'\n([a-zA-Z])\n', r'\1', text)
        
        # Fix hyphenation across lines
        text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)
        
        # Normalize paragraph breaks
        text = re.sub(r'\n\n\n+', '\n\n', text)
        
        # Fix multiple spaces
        text = re.sub(r' +', ' ', text)
        
        # Format lists properly
        text = self._format_lists(text)
        
        # Format code blocks
        text = self._format_code_blocks(text)
        
        # Format inline code and special terms
        text = self._format_inline_elements(text)
        
        return text
    
    def _format_markdown_content(self, title: str, section_number: str, 
                                 body: str, subsections: List[TOCItem] = None,
                                 chapter_title: str = None, is_intro: bool = False) -> str:
        """Format content as markdown with proper structure."""
        parts = []
        
        # Add frontmatter if configured
        if self.add_frontmatter:
            parts.append(self._generate_frontmatter(title, section_number, chapter_title))
        
        # Add title
        if not is_intro:
            parts.append(f"# {section_number} {title}\n")
        else:
            parts.append(f"# {title}\n")
        
        # Add body content
        formatted_body = self._clean_body_text(body)
        parts.append(formatted_body)
        
        return '\n\n'.join(parts)
    
    def _generate_frontmatter(self, title: str, section_number: str, 
                             chapter_title: str = None) -> str:
        """Generate YAML frontmatter."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        frontmatter = [
            "---",
            f"title: \"{title}\"",
            f"section: \"{section_number}\"",
        ]
        
        if chapter_title:
            frontmatter.append(f"chapter: \"{chapter_title}\"")
        
        frontmatter.extend([
            f"created: {today}",
            "---"
        ])
        
        return '\n'.join(frontmatter)
    
    def _format_code_blocks(self, text: str) -> str:
        """Detect and format code blocks."""
        lines = text.split('\n')
        result_lines = []
        in_code = False
        code_indent = 0
        
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)
            
            # Detect code blocks by consistent indentation of 4+ spaces
            # or by programming language patterns
            is_code_like = (
                current_indent >= 4 or
                re.match(r'^(def |class |import |from |if |for |while |return |print\(|>>>)', stripped) or
                re.match(r'^[a-z_]+\s*[=]\s*', stripped) or
                re.match(r'^\{|\}|^\[|\]', stripped)
            )
            
            if is_code_like and not in_code and stripped:
                result_lines.append('```')
                in_code = True
                code_indent = current_indent
            elif in_code and not is_code_like and stripped and current_indent < code_indent:
                result_lines.append('```')
                in_code = False
            
            result_lines.append(line)
        
        if in_code:
            result_lines.append('```')
        
        return '\n'.join(result_lines)
    
    def _format_lists(self, text: str) -> str:
        """Ensure lists are properly formatted."""
        # Fix numbered lists
        text = re.sub(r'^(\d+)\.\s+', r'\1. ', text, flags=re.MULTILINE)
        
        # Fix bullet lists
        text = re.sub(r'^[•·]\s*', '- ', text, flags=re.MULTILINE)
        
        # Ensure list items have proper spacing
        text = re.sub(r'\n(\d+\.\s|\-\s)', r'\n\n\1', text)
        
        return text
    
    def _format_inline_elements(self, text: str) -> str:
        """Format inline code and special elements."""
        # Detect technical terms that should be in backticks
        # Function names, class names, variable names
        tech_patterns = [
            r'\b(def|class|import|return|True|False|None)\b',
            r'\b([a-z_]+\(\))',  # function calls
            r'\b([A-Z][a-zA-Z]+Exception)\b',  # Exceptions
        ]
        
        for pattern in tech_patterns:
            text = re.sub(pattern, r'`\1`', text)
        
        return text
    
    def _insert_images_inline(self, body: str, images: List[ImageBlock]) -> str:
        """Insert images inline in the body text, above their captions."""
        if not images:
            return body
        
        # Sort images by page number and y_position
        sorted_images = sorted(images, key=lambda img: (img.page_num, img.y_position))
        
        # Find all figure/table references in the body text
        # Pattern matches: "Figure 1-1.", "Figure 1.1.", "Table 2-3.", etc.
        caption_pattern = re.compile(
            r'^(Figure|Fig\.|Table|Image)\s+(\d+[-\.]\d+)\.?\s+[A-Z].*$',
            re.MULTILINE | re.IGNORECASE
        )
        
        # Find all caption positions in the text
        caption_matches = list(caption_pattern.finditer(body))
        
        # Track which images have been inserted
        inserted_images = set()
        
        # Match images to captions by index (Figure 1-1 = first image on those pages, etc.)
        # Insert images in reverse order to maintain correct positions
        for i, match in enumerate(reversed(caption_matches)):
            if i < len(sorted_images):
                img = sorted_images[len(sorted_images) - 1 - i]
                img_markdown = self._format_single_image(img)
                
                # Find start of the line containing the caption
                insert_pos = match.start()
                line_start = body.rfind('\n', 0, insert_pos)
                if line_start == -1:
                    line_start = 0
                else:
                    line_start += 1
                
                body = body[:line_start] + img_markdown + '\n\n' + body[line_start:]
                inserted_images.add(id(img))
        
        # If no captions found, try alternative approach: match by pre-detected captions
        if not caption_matches:
            for img in sorted_images:
                if img.caption and id(img) not in inserted_images:
                    caption_text = img.caption[:50]
                    caption_search = re.escape(caption_text).replace(r'\ ', r'\s+')
                    
                    match = re.search(caption_search, body, re.IGNORECASE)
                    if match:
                        img_markdown = self._format_single_image(img)
                        insert_pos = match.start()
                        
                        line_start = body.rfind('\n', 0, insert_pos)
                        if line_start == -1:
                            line_start = 0
                        else:
                            line_start += 1
                        
                        body = body[:line_start] + img_markdown + '\n\n' + body[line_start:]
                        inserted_images.add(id(img))
        
        # Append any images that couldn't be matched to captions at the end
        remaining_images = [img for img in sorted_images if id(img) not in inserted_images]
        if remaining_images:
            body += '\n\n'
            for img in remaining_images:
                body += self._format_single_image(img) + '\n\n'
        
        return body
    
    def _format_single_image(self, img: ImageBlock) -> str:
        """Format a single image for markdown output."""
        # Use just the filename, not the full path
        filename = Path(img.image_path).name
        
        # Use caption if available, otherwise generic figure name
        alt_text = img.caption if img.caption else f"Figure"
        
        return f"![{alt_text}]({filename})"
    
    def _format_images_section(self, images: List[ImageBlock]) -> str:
        """Format images as a section (fallback, not used with inline images)."""
        if not images:
            return ""
        
        lines = []
        
        for i, img in enumerate(images):
            lines.append(self._format_single_image(img))
            if img.caption:
                lines.append(f"*{img.caption}*")
            lines.append("")
        
        return '\n'.join(lines)
    
    def _format_footnotes(self, footnotes: List[Footnote]) -> str:
        """Format footnotes for the markdown file."""
        if not footnotes:
            return ""
        
        lines = ["---", "## Notes\n"]
        
        for fn in footnotes:
            lines.append(f"`{fn.number}` {fn.text}")
            lines.append("")
        
        return '\n'.join(lines)
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to be filesystem-safe."""
        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Replace multiple spaces with single space
        filename = re.sub(r'\s+', ' ', filename)
        # Limit length
        if len(filename) > 100:
            filename = filename[:100].rsplit(' ', 1)[0]  # Cut at word boundary
        return filename.strip()
    
    def get_wikilink_for_section(self, section_number: str) -> str:
        """Get wikilink format for a section."""
        if section_number in self.created_files:
            file_path = self.created_files[section_number]
            # Remove .md extension for wikilink
            link_path = file_path.replace('.md', '')
            return f"[[{link_path}]]"
        return ""


if __name__ == "__main__":
    # Test
    import sys
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 3:
        from .toc_parser import TOCParser
        from .pdf_parser import PDFParser
        from .content_splitter import ContentSplitter
        
        toc_parser = TOCParser(sys.argv[1])
        toc_parser.parse()
        
        pdf_parser = PDFParser(sys.argv[2])
        pdf_parser.extract_blocks()
        
        splitter = ContentSplitter(toc_parser, pdf_parser)
        splitter.split_content()
        
        generator = MarkdownGenerator(sys.argv[3], toc_parser, splitter)
        files = generator.generate_all()
        
        print(f"\nGenerated {len(files)} files:")
        for num, path in files.items():
            print(f"  {num}: {path}")

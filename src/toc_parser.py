"""Parse table of contents markdown file to extract book structure."""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class TOCItem:
    """Represents an item in the table of contents."""
    level: int  # 1 for chapter, 2 for section, 3 for subsection
    number: str  # e.g., "1", "1.1", "1.1.1"
    title: str  # e.g., "Introduction to Building AI Applications"
    full_title: str  # With number prefix
    parent_number: Optional[str] = None  # Parent section number
    children: List['TOCItem'] = None
    page: Optional[int] = None  # 1-based start page (set when parsed from PDF outline)
    
    def __post_init__(self):
        if self.children is None:
            self.children = []
    
    def __repr__(self):
        return f"TOCItem(level={self.level}, number={self.number}, title={self.title})"


class TOCParser:
    """Parse markdown TOC file to extract hierarchical structure."""
    
    def __init__(self, toc_path: str):
        self.toc_path = toc_path
        self.items: List[TOCItem] = []
        self.chapter_map: Dict[str, TOCItem] = {}  # number -> item
        
    def parse(self) -> List[TOCItem]:
        """Parse the TOC file and return hierarchical structure."""
        with open(self.toc_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Skip YAML frontmatter if present
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                content = parts[2]
        
        lines = content.strip().split('\n')
        self._parse_lines(lines)
        return self.items
    
    def _parse_lines(self, lines: List[str]):
        """Parse lines and build hierarchical structure."""
        current_chapter = None
        current_section = None
        
        for line in lines:
            line = line.rstrip()
            if not line:
                continue
            
            # Check if it's a chapter (## N. Title)
            chapter_match = re.match(r'^##\s+(\d+)\.\s+(.+)$', line)
            if chapter_match:
                number = chapter_match.group(1)
                title = chapter_match.group(2).strip()
                item = TOCItem(
                    level=1,
                    number=number,
                    title=title,
                    full_title=f"{number}. {title}"
                )
                self.items.append(item)
                self.chapter_map[number] = item
                current_chapter = item
                current_section = None
                continue
            
            # Check if it's a section (- Title or - N.N Title)
            section_match = re.match(r'^-\s+(.+)$', line)
            if section_match and current_chapter:
                section_text = section_match.group(1).strip()
                
                # Try to extract section number if present
                num_match = re.match(r'^(\d+\.\d+)\.\s+(.+)$', section_text)
                if num_match:
                    number = num_match.group(1)
                    title = num_match.group(2).strip()
                else:
                    # Infer section number from position
                    section_idx = len(current_chapter.children) + 1
                    number = f"{current_chapter.number}.{section_idx}"
                    title = section_text
                
                item = TOCItem(
                    level=2,
                    number=number,
                    title=title,
                    full_title=f"{number} {title}",
                    parent_number=current_chapter.number
                )
                current_chapter.children.append(item)
                self.chapter_map[number] = item
                current_section = item
                continue
            
            # Check if it's a subsection (    - Title)
            subsection_match = re.match(r'^\s{4,}-\s+(.+)$', line)
            if subsection_match and current_section:
                subsection_text = subsection_match.group(1).strip()
                
                # Try to extract subsection number if present
                num_match = re.match(r'^(\d+\.\d+\.\d+)\.\s+(.+)$', subsection_text)
                if num_match:
                    number = num_match.group(1)
                    title = num_match.group(2).strip()
                else:
                    # Infer subsection number from position
                    subsection_idx = len(current_section.children) + 1
                    number = f"{current_section.number}.{subsection_idx}"
                    title = subsection_text
                
                item = TOCItem(
                    level=3,
                    number=number,
                    title=title,
                    full_title=f"{number} {title}",
                    parent_number=current_section.number
                )
                current_section.children.append(item)
                self.chapter_map[number] = item
                continue
    
    def get_chapter(self, number: str) -> Optional[TOCItem]:
        """Get chapter by number."""
        return self.chapter_map.get(number)
    
    def get_all_sections(self) -> List[TOCItem]:
        """Get all sections (level 2) flattened."""
        sections = []
        for chapter in self.items:
            sections.extend(chapter.children)
        return sections
    
    def get_section_context(self, section_number: str) -> Optional[Dict]:
        """Get context for a section including chapter info."""
        section = self.chapter_map.get(section_number)
        if not section or section.level != 2:
            return None
        
        chapter = self.chapter_map.get(section.parent_number)
        return {
            'chapter': chapter,
            'section': section,
            'subsections': section.children
        }
    
    def print_structure(self):
        """Print the parsed structure for debugging."""
        for chapter in self.items:
            print(f"Chapter {chapter.number}: {chapter.title}")
            for section in chapter.children:
                print(f"  Section {section.number}: {section.title}")
                for subsection in section.children:
                    print(f"    Subsection {subsection.number}: {subsection.title}")


if __name__ == "__main__":
    # Test the parser
    import sys
    if len(sys.argv) > 1:
        parser = TOCParser(sys.argv[1])
        parser.parse()
        parser.print_structure()

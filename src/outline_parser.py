"""Build book structure from a PDF's embedded outline (bookmarks).

This is a drop-in alternative to TOCParser for books that ship with an
embedded outline, so no external TOC markdown file is required. Hierarchy is
driven by the numbering in each heading title (e.g. "1", "1.2", "1.2.3")
rather than the outline's nesting depth, which is unreliable across books.
"""

import re
import logging
from typing import List, Dict, Optional

import fitz  # PyMuPDF

from .toc_parser import TOCItem

# Unnumbered headings to keep as sections of the current chapter.
KEEP_UNNUMBERED = {"summary", "exercises", "conclusion", "key takeaways"}


class OutlineTOCParser:
    """Parse a PDF's embedded outline into a TOCParser-compatible structure."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.items: List[TOCItem] = []          # top-level chapters
        self.chapter_map: Dict[str, TOCItem] = {}  # number -> item
        self.flat: List[TOCItem] = []           # all kept items, document order
        self.logger = logging.getLogger(__name__)

    def parse(self) -> List[TOCItem]:
        """Read the embedded outline and build the hierarchical structure."""
        doc = fitz.open(self.pdf_path)
        raw = doc.get_toc(simple=True)  # [[level, title, page], ...], 1-based pages
        doc.close()

        if not raw:
            self.logger.warning("PDF has no embedded outline")
            return self.items

        current_chapter: Optional[TOCItem] = None
        current_section: Optional[TOCItem] = None

        for _level, title, page in raw:
            title = (title or "").strip()
            if not title:
                continue

            number, clean_title, kind = self._classify(title)

            if kind == "chapter":
                current_chapter = self._add_chapter(number, clean_title, page)
                current_section = None
            elif kind == "section" and current_chapter:
                current_section = self._add_section(current_chapter, number, clean_title, page)
            elif kind == "subsection":
                parent = self._resolve_section(number, current_section)
                if parent:
                    self._add_subsection(parent, number, clean_title, page)
            elif kind == "extra" and current_chapter:
                # Unnumbered chapter-closer such as "Summary".
                current_section = self._add_section(current_chapter, None, clean_title, page)
            # everything else (front/back matter, "Part N" dividers) is skipped

        self.logger.info(
            f"Outline parsed: {len(self.items)} chapters, "
            f"{len(self.get_all_sections())} sections"
        )
        return self.items

    def _classify(self, title: str):
        """Return (number, clean_title, kind) for a heading title."""
        m = re.match(r'^(\d+(?:\.\d+){2,})\s+(.*)$', title)  # 1.2.3[.4...]
        if m:
            return m.group(1), m.group(2).strip(), "subsection"

        m = re.match(r'^(\d+\.\d+)\s+(.*)$', title)          # 1.2
        if m:
            return m.group(1), m.group(2).strip(), "section"

        m = re.match(r'^(?:Chapter\s+)?(\d+)[:.\s]+(.*)$', title, re.IGNORECASE)  # 1 / Chapter 1
        if m and not re.match(r'^Part\b', title, re.IGNORECASE):
            return m.group(1), m.group(2).strip(), "chapter"

        if title.lower() in KEEP_UNNUMBERED:
            return None, title, "extra"

        return None, title, "skip"

    def _add_chapter(self, number: str, title: str, page: int) -> TOCItem:
        if number in self.chapter_map:
            return self.chapter_map[number]
        item = TOCItem(level=1, number=number, title=title,
                       full_title=f"{number}. {title}", page=page)
        self.items.append(item)
        self.chapter_map[number] = item
        self.flat.append(item)
        return item

    def _add_section(self, chapter: TOCItem, number: Optional[str],
                     title: str, page: int) -> TOCItem:
        if number is None:  # positional number for unnumbered sections (e.g. Summary)
            number = f"{chapter.number}.{len(chapter.children) + 1}"
        item = TOCItem(level=2, number=number, title=title,
                       full_title=f"{number} {title}",
                       parent_number=chapter.number, page=page)
        chapter.children.append(item)
        self.chapter_map[number] = item
        self.flat.append(item)
        return item

    def _add_subsection(self, section: TOCItem, number: str,
                        title: str, page: int) -> TOCItem:
        item = TOCItem(level=3, number=number, title=title,
                       full_title=f"{number} {title}",
                       parent_number=section.number, page=page)
        section.children.append(item)
        self.chapter_map[number] = item
        self.flat.append(item)
        return item

    def _resolve_section(self, sub_number: str,
                         current_section: Optional[TOCItem]) -> Optional[TOCItem]:
        """Find the section a subsection belongs to (by its N.M prefix)."""
        parts = sub_number.split('.')
        parent_number = '.'.join(parts[:2])
        return self.chapter_map.get(parent_number) or current_section

    # --- TOCParser-compatible interface -------------------------------------

    def get_chapter(self, number: str) -> Optional[TOCItem]:
        return self.chapter_map.get(number)

    def get_all_sections(self) -> List[TOCItem]:
        sections = []
        for chapter in self.items:
            sections.extend(chapter.children)
        return sections

    def get_section_context(self, section_number: str) -> Optional[Dict]:
        section = self.chapter_map.get(section_number)
        if not section or section.level != 2:
            return None
        chapter = self.chapter_map.get(section.parent_number)
        return {'chapter': chapter, 'section': section, 'subsections': section.children}

    def to_markdown(self) -> str:
        """Render the structure as a markdown TOC (for wikilink generation)."""
        lines = []
        for chapter in self.items:
            lines.append(f"## {chapter.number}. {chapter.title}")
            for section in chapter.children:
                lines.append(f"- {section.number} {section.title}")
                for subsection in section.children:
                    lines.append(f"    - {subsection.title}")
            lines.append("")
        return '\n'.join(lines)

    def print_structure(self):
        for chapter in self.items:
            print(f"Chapter {chapter.number}: {chapter.title}")
            for section in chapter.children:
                print(f"  Section {section.number}: {section.title}")
                for subsection in section.children:
                    print(f"    Subsection {subsection.number}: {subsection.title}")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1:
        parser = OutlineTOCParser(sys.argv[1])
        parser.parse()
        parser.print_structure()

"""Build book structure from a PDF's embedded outline (bookmarks).

This is a drop-in alternative to TOCParser for books that ship with an
embedded outline, so no external TOC markdown file is required.

The outline's own nesting is used to build the hierarchy (it is the most
reliable signal across publishers). "Part" dividers are flattened, front/back
matter is dropped, and chapters/sections/subsections are then numbered
positionally — so books whose section numbering restarts in every chapter
(common in edited volumes) don't collide.
"""

import re
import logging
from typing import List, Dict, Optional

import fitz  # PyMuPDF

# Top-level entries that are not book content.
FRONT_MATTER = (
    'cover', 'copyright', 'title page', 'table of contents', 'contents',
    'brief contents', 'preface', 'foreword', 'acknowledg', 'about the',
    'about this', 'index', 'list of figures', 'list of tables', 'dedication',
    'glossary', 'bibliography', 'colophon', 'epigraph', 'frontmatter',
    'references', 'further reading',
)

from .toc_parser import TOCItem


class _Node:
    """A raw outline entry while building the tree."""

    def __init__(self, level: int, title: str, page: int):
        self.level = level
        self.title = title
        self.page = max(1, page)
        self.children: List['_Node'] = []


class OutlineTOCParser:
    """Parse a PDF's embedded outline into a TOCParser-compatible structure."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.items: List[TOCItem] = []          # top-level chapters
        self.chapter_map: Dict[str, TOCItem] = {}  # number -> item
        self.flat: List[TOCItem] = []           # all items, document order
        self.logger = logging.getLogger(__name__)

    def parse(self) -> List[TOCItem]:
        """Read the embedded outline and build the hierarchical structure."""
        doc = fitz.open(self.pdf_path)
        raw = doc.get_toc(simple=True)  # [[level, title, page], ...], 1-based pages
        doc.close()

        if not raw:
            self.logger.warning("PDF has no embedded outline")
            return self.items

        roots = self._build_tree(raw)
        roots = self._flatten_parts(roots)
        chapters = [r for r in roots if not self._is_front_matter(r.title)]
        chapters = self._drop_leading_leaves(chapters)
        self._build_items(chapters)

        self.logger.info(
            f"Outline parsed: {len(self.items)} chapters, "
            f"{len(self.get_all_sections())} sections"
        )
        return self.items

    # --- tree building ------------------------------------------------------

    def _build_tree(self, raw) -> List[_Node]:
        """Turn the flat [level, title, page] list into a forest."""
        roots: List[_Node] = []
        stack: List[_Node] = []
        for level, title, page in raw:
            title = (title or "").strip()
            if not title:
                continue
            node = _Node(level, title, page)
            while stack and stack[-1].level >= level:
                stack.pop()
            if stack:
                stack[-1].children.append(node)
            else:
                roots.append(node)
            stack.append(node)
        return roots

    def _flatten_parts(self, roots: List[_Node]) -> List[_Node]:
        """Replace top-level 'Part' dividers with their child chapters."""
        flat: List[_Node] = []
        for root in roots:
            if self._is_part(root.title) and root.children:
                flat.extend(root.children)
            else:
                flat.append(root)
        return flat

    def _drop_leading_leaves(self, roots: List[_Node]) -> List[_Node]:
        """Drop title page / leading leaves that precede the first real chapter.

        A real chapter has sections (children); a title page is a childless leaf
        at the very front. Only applied when the book has nested structure.
        """
        if not any(r.children for r in roots):
            return roots
        first = next(i for i, r in enumerate(roots) if r.children)
        return roots[first:]

    def _build_items(self, chapters: List[_Node]):
        """Convert chapter nodes into the numbered TOCItem hierarchy."""
        for c_idx, ch in enumerate(chapters, 1):
            chapter = self._make_item(1, str(c_idx), ch.title, None, ch.page)
            self.items.append(chapter)
            self.chapter_map[chapter.number] = chapter
            self.flat.append(chapter)

            section_nodes = ch.children or [ch]  # chapter with no sections -> itself
            for s_idx, sn in enumerate(section_nodes, 1):
                snum = f"{c_idx}.{s_idx}"
                section = self._make_item(2, snum, sn.title, chapter.number, sn.page)
                chapter.children.append(section)
                self.chapter_map[snum] = section
                self.flat.append(section)

                # Flatten everything below a section into a single subsection list.
                descendants = [] if sn is ch else self._descendants(sn)
                for k_idx, dn in enumerate(descendants, 1):
                    knum = f"{snum}.{k_idx}"
                    sub = self._make_item(3, knum, dn.title, snum, dn.page)
                    section.children.append(sub)
                    self.chapter_map[knum] = sub
                    self.flat.append(sub)

    def _descendants(self, node: _Node) -> List[_Node]:
        """Pre-order list of all nodes beneath a section."""
        out = []
        for child in node.children:
            out.append(child)
            out.extend(self._descendants(child))
        return out

    def _make_item(self, level: int, number: str, raw_title: str,
                   parent: Optional[str], page: int) -> TOCItem:
        title = self._clean_title(raw_title)
        prefix = number + ("." if level == 1 else " ")
        return TOCItem(level=level, number=number, title=title,
                       full_title=f"{prefix}{title}", parent_number=parent, page=page)

    # --- title / divider helpers --------------------------------------------

    def _clean_title(self, title: str) -> str:
        """Strip leading numbering so it isn't duplicated by positional numbers."""
        t = title.strip()
        t = re.sub(r'^Chapter\s+\d+\s*[:.\-]?\s*', '', t, flags=re.IGNORECASE)
        t = re.sub(r'^\d+(?:\.\d+)*\.?\s+', '', t)
        return t.strip() or title.strip()

    def _is_part(self, title: str) -> bool:
        t = title.strip()
        return bool(re.match(r'^Part\b', t, re.IGNORECASE) or
                    re.match(r'^[IVXLCDM]+\s*[:.]\s+\S', t))

    def _is_front_matter(self, title: str) -> bool:
        t = title.strip().lower()
        return any(t == k or t.startswith(k) for k in FRONT_MATTER)

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

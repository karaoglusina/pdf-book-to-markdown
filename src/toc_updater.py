"""Update TOC markdown file with wikilinks to generated files."""

import re
import logging
from pathlib import Path
from typing import Dict, List
from .toc_parser import TOCParser, TOCItem


class TOCUpdater:
    """Update TOC file with wikilinks to generated markdown files."""
    
    def __init__(self, toc_path: str, created_files: Dict[str, str]):
        self.toc_path = toc_path
        self.created_files = created_files
        self.logger = logging.getLogger(__name__)
    
    def update_toc(self, output_path: str = None) -> str:
        """Update TOC with wikilinks and optionally save to new file."""
        self.logger.info(f"Updating TOC file: {self.toc_path}")
        
        # Read original TOC
        with open(self.toc_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split into frontmatter and content
        frontmatter = ""
        toc_content = content
        
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter = f"---{parts[1]}---\n"
                toc_content = parts[2]
        
        # Update content with wikilinks
        updated_content = self._add_wikilinks(toc_content)
        
        # Combine frontmatter and updated content
        full_content = frontmatter + updated_content
        
        # Determine output path
        if output_path is None:
            output_path = self.toc_path
        
        # Write updated TOC
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
        
        self.logger.info(f"Updated TOC saved to: {output_path}")
        return full_content
    
    def _add_wikilinks(self, content: str) -> str:
        """Add wikilinks to chapter and section items."""
        lines = content.split('\n')
        updated_lines = []
        
        for line in lines:
            updated_line = line
            
            # Check if line is a chapter (## N. Title)
            chapter_match = re.match(r'^(##\s+)(\d+)\.\s+(.+)$', line)
            if chapter_match:
                prefix = chapter_match.group(1)
                chapter_num = chapter_match.group(2)
                chapter_title = chapter_match.group(3).strip()
                
                # Check if we have an intro file for this chapter
                intro_key = f"{chapter_num}_intro"
                if intro_key in self.created_files:
                    file_path = self.created_files[intro_key]
                    # Create wikilink for chapter title
                    wikilink = self._create_wikilink(file_path, f"{chapter_num}. {chapter_title}")
                    updated_line = f"## {wikilink}"
                
                updated_lines.append(updated_line)
                continue
            
            # Check if line is a section (starts with -)
            section_match = re.match(r'^(-\s+)(.+)$', line)
            if section_match:
                prefix = section_match.group(1)
                section_text = section_match.group(2).strip()
                
                # Try to extract section number
                num_match = re.match(r'^(\d+\.\d+)\.?\s+(.+)$', section_text)
                if num_match:
                    section_num = num_match.group(1)
                    section_title = num_match.group(2)
                else:
                    # Try to infer from created files
                    section_num = self._find_section_number(section_text)
                    section_title = section_text
                
                # Check if we have a file for this section
                if section_num and section_num in self.created_files:
                    file_path = self.created_files[section_num]
                    # Create wikilink
                    wikilink = self._create_wikilink(file_path, section_title)
                    updated_line = f"{prefix}{wikilink}"
            
            updated_lines.append(updated_line)
        
        return '\n'.join(updated_lines)
    
    def _find_section_number(self, section_text: str) -> str:
        """Try to find section number by matching text."""
        for section_num, file_path in self.created_files.items():
            if section_text.lower() in file_path.lower():
                return section_num
        return ""
    
    def _create_wikilink(self, file_path: str, display_text: str = None) -> str:
        """Create wikilink from file path."""
        # Remove .md extension
        link_path = file_path.replace('.md', '')
        
        if display_text:
            # Use display text if different from filename
            return f"[[{link_path}|{display_text}]]"
        else:
            return f"[[{link_path}]]"
    
    def create_backup(self, backup_dir: str = None) -> str:
        """Create backup of original TOC file."""
        if backup_dir:
            # Save backup to specified directory
            from pathlib import Path
            backup_filename = Path(self.toc_path).name + ".backup"
            backup_path = str(Path(backup_dir) / backup_filename)
        else:
            backup_path = f"{self.toc_path}.backup"
        
        with open(self.toc_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        self.logger.info(f"Created backup: {backup_path}")
        return backup_path


if __name__ == "__main__":
    # Test
    import sys
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1:
        # Mock created files for testing
        created_files = {
            "1.1": "01. Introduction/1.1 The Rise of AI Engineering.md",
            "1.2": "01. Introduction/1.2 Foundation Model Use Cases.md"
        }
        
        updater = TOCUpdater(sys.argv[1], created_files)
        updater.create_backup()
        updater.update_toc(sys.argv[1] + ".updated")

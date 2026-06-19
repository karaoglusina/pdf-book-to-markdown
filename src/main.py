"""Main orchestration script for PDF to Markdown conversion."""

import yaml
import logging
import sys
from pathlib import Path
from typing import Dict

from .toc_parser import TOCParser
from .pdf_parser import PDFParser
from .content_splitter import ContentSplitter
from .markdown_generator import MarkdownGenerator
from .toc_updater import TOCUpdater


class PDFToMarkdownConverter:
    """Main converter class that orchestrates the entire pipeline."""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self._setup_logging()
        
        self.logger = logging.getLogger(__name__)
        
        # Components
        self.toc_parser: TOCParser = None
        self.pdf_parser: PDFParser = None
        self.content_splitter: ContentSplitter = None
        self.markdown_generator: MarkdownGenerator = None
        self.toc_updater: TOCUpdater = None
        
    def _load_config(self) -> Dict:
        """Load configuration from YAML file."""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    
    def _setup_logging(self):
        """Setup logging configuration."""
        log_level = self.config.get('logging', {}).get('level', 'INFO')
        log_file = self.config.get('logging', {}).get('file', 'pdf_conversion.log')
        
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
    
    def run(self):
        """Run the complete conversion pipeline."""
        try:
            self.logger.info("="*80)
            self.logger.info("Starting PDF to Markdown conversion")
            self.logger.info("="*80)
            
            # Step 1: Parse TOC
            self.logger.info("\n[Step 1/6] Parsing Table of Contents...")
            self._parse_toc()
            
            # Step 2: Extract PDF content
            self.logger.info("\n[Step 2/6] Extracting PDF content...")
            self._extract_pdf()
            
            # Step 3: Split content by sections
            self.logger.info("\n[Step 3/6] Splitting content by sections...")
            self._split_content()
            
            # Step 4: Generate markdown files
            self.logger.info("\n[Step 4/6] Generating markdown files...")
            created_files = self._generate_markdown()
            
            # Step 5: Update TOC with wikilinks
            self.logger.info("\n[Step 5/6] Updating TOC with wikilinks...")
            self._update_toc(created_files)
            
            # Step 6: Generate summary report
            self.logger.info("\n[Step 6/6] Generating summary report...")
            self._generate_report(created_files)
            
            self.logger.info("\n" + "="*80)
            self.logger.info("Conversion completed successfully!")
            self.logger.info("="*80)
            
        except Exception as e:
            self.logger.error(f"Conversion failed: {e}", exc_info=True)
            raise
    
    def _parse_toc(self):
        """Parse table of contents."""
        toc_path = self.config['toc_path']
        self.logger.info(f"Loading TOC from: {toc_path}")
        
        self.toc_parser = TOCParser(toc_path)
        items = self.toc_parser.parse()
        
        self.logger.info(f"Parsed {len(items)} chapters")
        
        # Log structure
        total_sections = sum(len(chapter.children) for chapter in items)
        self.logger.info(f"Found {total_sections} sections")
        
        if self.logger.level <= logging.DEBUG:
            self.toc_parser.print_structure()
    
    def _extract_pdf(self):
        """Extract content from PDF."""
        pdf_path = self.config['pdf_path']
        output_dir = self.config['output_dir']
        self.logger.info(f"Extracting from PDF: {pdf_path}")
        
        header_config = self.config.get('header_detection', {})
        self.pdf_parser = PDFParser(pdf_path, header_config, output_dir=output_dir)
        
        blocks, images, footnotes = self.pdf_parser.extract_all()
        self.logger.info(f"Extracted {len(blocks)} text blocks, {len(images)} images, {len(footnotes)} footnotes")
        
        # Log font statistics and content summary
        stats = self.pdf_parser.get_font_size_stats()
        if stats:
            self.logger.info(f"Font size range: {stats['min']:.1f} - {stats['max']:.1f}")
            self.logger.info(f"Average font size: {stats['avg']:.1f}")
        
        if images:
            self.logger.info(f"Images saved to: {self.pdf_parser.image_dir}")
        if footnotes:
            self.logger.info(f"Detected {len(footnotes)} footnotes")
    
    def _split_content(self):
        """Split content according to TOC structure."""
        self.content_splitter = ContentSplitter(self.toc_parser, self.pdf_parser)
        section_contents = self.content_splitter.split_content()
        
        # Log quality metrics
        high_confidence = sum(1 for c in section_contents.values() if c.confidence > 0.7)
        low_confidence = sum(1 for c in section_contents.values() if c.confidence < 0.4)
        
        self.logger.info(f"Split into {len(section_contents)} sections")
        self.logger.info(f"High confidence matches: {high_confidence}")
        if low_confidence > 0:
            self.logger.warning(f"Low confidence matches: {low_confidence}")
    
    def _generate_markdown(self) -> Dict[str, str]:
        """Generate markdown files."""
        output_dir = self.config['output_dir']
        markdown_config = self.config.get('markdown', {})
        
        self.markdown_generator = MarkdownGenerator(
            output_dir, 
            self.toc_parser, 
            self.content_splitter,
            markdown_config
        )
        
        created_files = self.markdown_generator.generate_all()
        
        self.logger.info(f"Generated {len(created_files)} markdown files")
        self.logger.info(f"Output directory: {output_dir}")
        
        return created_files
    
    def _update_toc(self, created_files: Dict[str, str]):
        """Update TOC with wikilinks."""
        toc_path = self.config['toc_path']
        output_dir = Path(self.config['output_dir'])
        
        self.toc_updater = TOCUpdater(toc_path, created_files)
        
        # Create backup in output directory
        backup_path = self.toc_updater.create_backup(backup_dir=str(output_dir))
        self.logger.info(f"Created TOC backup: {backup_path}")
        
        # Update TOC and save to output directory with wikilinks
        updated_toc_path = output_dir / "TOC_with_wikilinks.md"
        self.toc_updater.update_toc(str(updated_toc_path))
        self.logger.info(f"Updated TOC with wikilinks saved to: {updated_toc_path}")
    
    def _generate_report(self, created_files: Dict[str, str]):
        """Generate summary report."""
        output_dir = Path(self.config['output_dir'])
        report_path = output_dir / "conversion_report.md"
        
        sections = self.content_splitter.section_contents
        
        # Build report
        lines = [
            "# PDF to Markdown Conversion Report",
            f"\nGenerated: {self._get_timestamp()}",
            f"\n## Summary\n",
            f"- Total files created: {len(created_files)}",
            f"- Total sections processed: {len(sections)}",
            f"- Output directory: `{output_dir}`",
            "\n## Generated Files\n"
        ]
        
        # List files by chapter
        for chapter in self.toc_parser.items:
            lines.append(f"\n### Chapter {chapter.number}: {chapter.title}\n")
            
            for section in chapter.children:
                if section.number in created_files:
                    file_path = created_files[section.number]
                    content = sections.get(section.number)
                    
                    confidence = content.confidence if content else 0
                    emoji = "✅" if confidence > 0.7 else "⚠️" if confidence > 0.4 else "❌"
                    
                    lines.append(f"- {emoji} `{file_path}`")
                    if content:
                        lines.append(f"  - Pages: {content.page_start}-{content.page_end}")
                        lines.append(f"  - Confidence: {confidence:.2f}")
                        lines.append(f"  - Content length: {len(content.full_text)} chars")
        
        # Quality notes
        low_confidence_sections = [
            s for s in sections.values() if s.confidence < 0.4
        ]
        
        if low_confidence_sections:
            lines.append("\n## ⚠️ Sections Needing Review\n")
            lines.append("The following sections had low confidence matches:\n")
            for section in low_confidence_sections:
                lines.append(f"- Section {section.section.number}: {section.section.title} "
                           f"(confidence: {section.confidence:.2f})")
        
        report_content = '\n'.join(lines)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        self.logger.info(f"Report saved to: {report_path}")
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    """Main entry point."""
    # Get config path from command line or use default
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    
    # Check if config exists
    if not Path(config_path).exists():
        print(f"Error: Config file not found: {config_path}")
        print("Usage: python -m src.main [config.yaml]")
        sys.exit(1)
    
    # Run converter
    converter = PDFToMarkdownConverter(config_path)
    converter.run()


if __name__ == "__main__":
    main()

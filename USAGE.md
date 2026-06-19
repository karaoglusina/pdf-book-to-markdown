# PDF to Markdown Converter - Usage Guide

## Quick Start

### 1. Installation

```bash
cd pdf-book-to-markdown
pip install -r requirements.txt
```

### 2. Configuration

Edit `config.yaml` to set your paths:

```yaml
pdf_path: "/path/to/your/book.pdf"
toc_path: "/path/to/your/toc.md"
output_dir: "./output"
```

### 3. Run Conversion

```bash
python3 -m src.main
```

## Output Structure

The converter generates:

```
output/
├── 01. Chapter Name/
│   ├── _intro.md                    # Chapter introduction
│   ├── 1.1 Section Name.md          # Section with all subsections
│   ├── 1.2 Another Section.md
│   └── ...
├── 02. Next Chapter/
│   └── ...
├── TOC_with_wikilinks.md            # Updated TOC with wikilinks
└── conversion_report.md             # Detailed conversion report
```

## Output Files

### 1. Section Markdown Files

Each section file contains:
- YAML frontmatter with metadata (title, section number, chapter)
- Section heading
- Full content including all subsections
- List of subsections at the end

Example:
```markdown
---
title: "The Rise of AI Engineering"
section: "1.1"
chapter: "Introduction to Building AI Applications"
created: 2026-01-12
---

# 1.1 The Rise of AI Engineering

[Content here...]

## Subsections

- 1.1.1 From Language Models to Large Language Models
- 1.1.2 From Large Language Models to Foundation Models
```

### 2. TOC with Wikilinks

The TOC file is updated with Obsidian-style wikilinks:

```markdown
## 1. Introduction to Building AI Applications

- [[01. Introduction/1.1 The Rise of AI Engineering|The Rise of AI Engineering]]
    - From Language Models to Large Language Models
    - From Large Language Models to Foundation Models
```

### 3. Conversion Report

Shows:
- Total files created
- Confidence scores for each section
- Content length statistics
- Sections needing manual review (if any)

## For AI Engineering Book

The conversion has been successfully completed for the AI Engineering book:

**Results:**
- ✅ 52 markdown files generated
- ✅ 10 chapters processed
- ✅ 42 sections extracted
- ✅ All sections matched with high confidence (1.20)
- ✅ TOC updated with wikilinks

**Location:**
`output/AI engineering/`

**Files include:**
- Chapter intro files (`_intro.md`)
- Section files with full content
- Updated TOC with wikilinks
- Detailed conversion report

## Tips

1. **Review the Report**: Always check `conversion_report.md` after conversion
2. **Low Confidence Sections**: Manually review sections with confidence < 0.4
3. **Missing Content**: If a section has 0 chars, the header detection may have failed
4. **Customization**: Adjust font size thresholds in `config.yaml` if needed

## Troubleshooting

### No Content Extracted

If sections have no content:
- Check if PDF is text-based (not scanned images)
- Adjust `min_font_size_chapter` and `min_font_size_section` in config
- Run with `logging.level: DEBUG` for detailed info

### Wrong Section Splits

If sections are split incorrectly:
- Verify your TOC file matches the PDF structure
- Check the conversion report for confidence scores
- Manually adjust sections with low confidence

### Missing Sections

If some sections are missing:
- Ensure TOC structure matches PDF exactly
- Check logs for warnings about unmatched sections
- Verify section titles in TOC match PDF headers

## Advanced Usage

### Custom TOC Structure

Your TOC markdown should follow this format:

```markdown
## 1. Chapter Title
- Section Title
    - Subsection Title
    - Another Subsection

## 2. Next Chapter
- Next Section
```

### Processing Other Books

To convert other books:

1. Create a TOC markdown file for the book
2. Update `config.yaml` with new paths
3. Run the converter
4. Review the conversion report

## File Formats

### Input Requirements

- **PDF**: Text-based PDF (not scanned images)
- **TOC**: Markdown file with hierarchical bullet structure

### Output Format

- **Markdown**: Standard markdown with YAML frontmatter
- **Wikilinks**: Obsidian-style `[[path|display text]]`
- **Structure**: One section per file, organized by chapters

## Next Steps

After conversion:

1. Review `conversion_report.md`
2. Check a few sample sections for quality
3. Manually review any low-confidence sections
4. Import into your note-taking system (Obsidian, etc.)
5. Enjoy your structured markdown knowledge base!

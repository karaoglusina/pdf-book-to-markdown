# PDF to Markdown Converter

A Python tool to convert technical PDF books into structured markdown knowledge bases with proper folder organization and wikilinks.

## Features

- **Intelligent Structure Detection**: Automatically detects chapters, sections, and subsections using font analysis
- **TOC-Driven Splitting**: Uses existing table of contents to guide content organization
- **Hierarchical Output**: Creates folder structure matching book organization
- **Wikilink Integration**: Updates TOC with links to generated markdown files
- **Robust Extraction**: Multiple fallback strategies for header detection

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Edit `config.yaml` to set:
- Input PDF and TOC paths
- Output directory
- Splitting depth (chapters, sections, or all levels)
- Header detection parameters

## Usage

```bash
python src/main.py
```

Or import as a module:

```python
from src.main import PDFToMarkdownConverter

converter = PDFToMarkdownConverter("config.yaml")
converter.run()
```

## Output Structure

```
AI engineering/
├── 01. Introduction to Building AI Applications/
│   ├── _intro.md
│   ├── 1.1 The Rise of AI Engineering.md
│   ├── 1.2 Foundation Model Use Cases.md
│   └── ...
├── 02. Understanding Foundation Models/
│   ├── _intro.md
│   ├── 2.1 Training Data.md
│   └── ...
```

## Project Structure

- `src/pdf_parser.py`: PDF text extraction with structure detection
- `src/toc_parser.py`: Parse TOC markdown files
- `src/content_splitter.py`: Split PDF content by sections
- `src/markdown_generator.py`: Generate organized markdown files
- `src/main.py`: Main orchestration script

## Requirements

- Python 3.8+
- PyMuPDF (fitz)
- pdfplumber
- PyYAML

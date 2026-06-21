# PDF to Markdown Converter

A Python tool to convert technical PDF books into structured markdown knowledge bases with proper folder organization and wikilinks.

## Features

- **Embedded Outline Support**: Uses the PDF's built-in outline (bookmarks) by default — no table of contents file needed
- **Intelligent Structure Detection**: Detects chapters, sections, and subsections from heading numbering, with font analysis as a fallback
- **Optional TOC-Driven Splitting**: Supply your own markdown table of contents when a PDF has no usable outline
- **Hierarchical Output**: Creates folder structure matching book organization
- **Wikilink Integration**: Generates a TOC with links to the created markdown files

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

Run a conversion straight from the command line — no need to edit `config.yaml`.
By default the structure is read from the PDF's embedded outline, so only the
PDF is required:

```bash
python -m src.main --pdf book.pdf
```

This writes to `output/<pdf-name>/`. Override the destination with `-o/--output`:

```bash
python -m src.main --pdf book.pdf -o "output/My Book"
```

If a PDF has no embedded outline, supply your own markdown TOC with `--toc`:

```bash
python -m src.main --pdf book.pdf --toc toc.md
```

Flags override the config file, which is still used for all other defaults
(font thresholds, splitting depth, etc.). To run purely from a config file:

```bash
python -m src.main                 # uses config.yaml
python -m src.main my-config.yaml  # uses a specific config
```

| Flag | Overrides | Description |
|------|-----------|-------------|
| `--pdf` | `pdf_path` | Input PDF |
| `--toc` | `toc_path` | Markdown TOC (optional; embedded outline used if omitted) |
| `-o`, `--output` | `output_dir` | Output directory (defaults to `output/<pdf-name>`) |

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

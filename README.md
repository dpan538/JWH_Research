# JWH Research: 苏皖沪古籍县志调查

This repository contains the analysis pipeline and pilot outputs for a Jiangsu / Anhui / Shanghai local gazetteer corpus.

It intentionally does **not** store the original PDF, DOC, or RAR source files. The original corpus is about 11GB and should remain outside Git or be handled later through a dedicated archive / release / large-file storage strategy.

## Repository Contents

- `scripts/`: staged processing pipeline.
- `data/manifest/`: normalized source manifest and load summaries.
- `data/metadata/`: stable `doc_id` map, pilot selection, page inventory, and OCR queue.
- `data/text_raw/`: pilot existing-text extraction JSONL.
- `data/text_clean/`: pilot cleaned text JSONL.
- `data/text_annotated/`: pilot semantic tag JSONL.
- `data/indexes/`: lightweight document, page, and tag indexes.
- `data/quality_control/`: extraction issues and pilot processing reports.
- `data/reading_exports/`: Markdown reading exports for the pilot set.

## Important Boundary

The `.gitignore` blocks `*.pdf`, `*.doc`, `*.docx`, `*.rar`, archive files, OCR scratch images, and temporary downloads. This keeps the repository focused on analysis rather than raw scanned files.

The first milestone intentionally avoids uncontrolled full-corpus OCR. It:

1. Loads the existing scan manifest.
2. Generates stable `doc_id` values while preserving original file identity.
3. Selects a balanced 20-document pilot set.
4. Extracts existing PDF text layers and readable DOC text.
5. Detects page-level OCR needs.
6. Prepares a pilot OCR queue.
7. Produces raw page JSONL, clean text JSONL, annotated JSONL, Markdown reading exports, indexes, and quality reports.

Run from this directory:

```bash
python3 scripts/01_load_manifest.py
python3 scripts/02_generate_doc_ids.py
python3 scripts/03_select_pilot_set.py
python3 scripts/04_extract_existing_text.py
python3 scripts/05_detect_ocr_pages.py
python3 scripts/06_prepare_ocr_queue.py
python3 scripts/08_clean_text.py
python3 scripts/09_annotate_entities.py
python3 scripts/10_export_reading_markdown.py
python3 scripts/11_generate_index.py
python3 scripts/12_quality_report.py
python3 scripts/13_build_reading_export_layer.py
```

`scripts/07_run_ocr_pilot.py` is safe by default and only writes a dry-run plan. Real OCR requires `--execute`.

The structured reading layer is written to `data/reading_exports/documents/{doc_id}/` with:

- `raw_text.md`
- `clean_reading.md`
- `annotated_reading.md`
- `summary.md`

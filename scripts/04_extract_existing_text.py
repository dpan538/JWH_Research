from __future__ import annotations

import json
import subprocess
from pathlib import Path

import fitz

from common import (
    QC_DIR,
    TEXT_RAW_DIR,
    TEXT_THRESHOLD,
    clean_whitespace,
    doc_text_from_binary,
    read_jsonl,
    resolve_source_path,
    split_doc_text,
    write_json,
    write_jsonl,
    METADATA_DIR,
)


def extract_pdf(doc: dict, path: Path) -> tuple[list[dict], list[dict]]:
    pages = []
    issues = []
    try:
        pdf = fitz.open(str(path))
    except Exception as exc:
        issues.append({"doc_id": doc["doc_id"], "issue_type": "unreadable_pdf", "message": repr(exc)})
        return pages, issues

    for page_index in range(pdf.page_count):
        page_number = page_index + 1
        try:
            page = pdf.load_page(page_index)
            text = clean_whitespace(page.get_text("text") or "")
            image_count = len(page.get_images(full=False))
            char_count = len(text)
            flags = []
            if char_count < TEXT_THRESHOLD:
                flags.append("needs_ocr")
            if char_count == 0 and image_count == 0:
                flags.append("possible_blank_page")
            pages.append(
                {
                    "doc_id": doc["doc_id"],
                    "source_file_name": doc["source_file_name"],
                    "page_number": page_number,
                    "source_page_type": "pdf_page",
                    "text": text,
                    "char_count": char_count,
                    "has_text_layer": char_count >= TEXT_THRESHOLD,
                    "needs_ocr": char_count < TEXT_THRESHOLD,
                    "image_count": image_count,
                    "extraction_method": "pymupdf_text_layer",
                    "qc_flags": flags,
                }
            )
        except Exception as exc:
            issues.append({"doc_id": doc["doc_id"], "page_number": page_number, "issue_type": "page_read_error", "message": repr(exc)})
            pages.append(
                {
                    "doc_id": doc["doc_id"],
                    "source_file_name": doc["source_file_name"],
                    "page_number": page_number,
                    "source_page_type": "pdf_page",
                    "text": "",
                    "char_count": 0,
                    "has_text_layer": False,
                    "needs_ocr": True,
                    "image_count": None,
                    "extraction_method": "pymupdf_text_layer",
                    "qc_flags": ["page_read_error", "needs_ocr"],
                }
            )
    pdf.close()
    return pages, issues


def extract_doc(doc: dict, path: Path) -> tuple[list[dict], list[dict]]:
    pages = []
    issues = []
    try:
        text, diagnostics = doc_text_from_binary(path)
    except Exception as exc:
        issues.append({"doc_id": doc["doc_id"], "issue_type": "unreadable_doc", "message": repr(exc)})
        return pages, issues

    if diagnostics["confidence"].startswith("low"):
        issues.append({"doc_id": doc["doc_id"], "issue_type": "low_confidence_doc_text", "message": json.dumps(diagnostics, ensure_ascii=False)})

    for chunk_number, chunk in enumerate(split_doc_text(text), start=1):
        chunk = clean_whitespace(chunk)
        pages.append(
            {
                "doc_id": doc["doc_id"],
                "source_file_name": doc["source_file_name"],
                "page_number": chunk_number,
                "source_page_type": "doc_chunk",
                "text": chunk,
                "char_count": len(chunk),
                "has_text_layer": bool(chunk) and not diagnostics["confidence"].startswith("low"),
                "needs_ocr": diagnostics["confidence"].startswith("low"),
                "image_count": None,
                "extraction_method": diagnostics["method"],
                "doc_text_diagnostics": diagnostics,
                "qc_flags": ["low_confidence_doc_text"] if diagnostics["confidence"].startswith("low") else [],
            }
        )
    return pages, issues


def inspect_archive(doc: dict, path: Path) -> tuple[list[dict], list[dict]]:
    issues = []
    try:
        listing = subprocess.run(["bsdtar", "-tf", str(path)], capture_output=True, text=True, timeout=30)
        if listing.returncode != 0:
            issues.append({"doc_id": doc["doc_id"], "issue_type": "archive_list_error", "message": listing.stderr.strip()})
        else:
            issues.append({"doc_id": doc["doc_id"], "issue_type": "archive_not_extracted_in_text_stage", "message": listing.stdout.strip()})
    except Exception as exc:
        issues.append({"doc_id": doc["doc_id"], "issue_type": "archive_inspection_error", "message": repr(exc)})
    return [], issues


def main() -> None:
    pilot_docs = read_jsonl(METADATA_DIR / "pilot_documents.jsonl")
    if not pilot_docs:
        raise FileNotFoundError("Run 03_select_pilot_set.py first.")

    all_pages = []
    all_issues = []
    doc_summaries = []

    for doc in pilot_docs:
        path = resolve_source_path(doc)
        doc_issues = []
        if not path.exists():
            pages = []
            doc_issues.append({"doc_id": doc["doc_id"], "issue_type": "missing_source_file", "message": str(path)})
        elif doc.get("is_archive") or path.suffix.lower() == ".rar":
            pages, doc_issues = inspect_archive(doc, path)
        elif str(doc.get("source_file_name", "")).lower().endswith(".doc"):
            pages, doc_issues = extract_doc(doc, path)
        elif ".pdf" in str(doc.get("source_file_name", "")).lower():
            pages, doc_issues = extract_pdf(doc, path)
        else:
            pages = []
            doc_issues.append({"doc_id": doc["doc_id"], "issue_type": "unsupported_file_type", "message": str(path)})

        write_jsonl(TEXT_RAW_DIR / f"{doc['doc_id']}.jsonl", pages)
        all_pages.extend(pages)
        all_issues.extend(doc_issues)
        doc_summaries.append(
            {
                "doc_id": doc["doc_id"],
                "source_file_name": doc["source_file_name"],
                "pilot_bucket": doc.get("pilot_bucket"),
                "page_or_chunk_records": len(pages),
                "text_chars_extracted": sum(page.get("char_count", 0) for page in pages),
                "records_needing_ocr": sum(1 for page in pages if page.get("needs_ocr")),
                "issue_count": len(doc_issues),
            }
        )

    write_jsonl(TEXT_RAW_DIR / "pilot_pages_raw.jsonl", all_pages)
    write_jsonl(QC_DIR / "pilot_extraction_issues.jsonl", all_issues)
    write_json(METADATA_DIR / "pilot_extraction_summary.json", {"documents": doc_summaries, "issue_count": len(all_issues)})
    print(f"Extracted page/chunk records: {len(all_pages)}")
    print(f"Extraction issues: {len(all_issues)}")


if __name__ == "__main__":
    main()


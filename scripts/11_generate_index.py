from __future__ import annotations

import csv
from collections import Counter, defaultdict

from common import INDEXES_DIR, METADATA_DIR, TEXT_ANNOTATED_DIR, read_jsonl, write_json, write_jsonl


def snippet(text: str, limit: int = 240) -> str:
    text = " ".join((text or "").split())
    return text[:limit]


def main() -> None:
    docs = read_jsonl(METADATA_DIR / "pilot_documents.jsonl")
    pages = read_jsonl(TEXT_ANNOTATED_DIR / "pilot_pages_annotated.jsonl")
    if not docs:
        raise FileNotFoundError("Run 03_select_pilot_set.py first.")

    by_doc_pages: dict[str, list[dict]] = defaultdict(list)
    tag_index: dict[str, set[str]] = defaultdict(set)
    search_pages = []
    for page in pages:
        by_doc_pages[page["doc_id"]].append(page)
        for tag in page.get("semantic_tag_keys", []):
            tag_index[tag].add(page["doc_id"])
        if page.get("text_clean"):
            search_pages.append(
                {
                    "doc_id": page["doc_id"],
                    "page_number": page.get("page_number"),
                    "source_page_type": page.get("source_page_type"),
                    "snippet": snippet(page.get("text_clean", "")),
                    "semantic_tag_keys": page.get("semantic_tag_keys", []),
                }
            )

    document_index = []
    for doc in docs:
        doc_pages = by_doc_pages.get(doc["doc_id"], [])
        tag_counts = Counter(tag for page in doc_pages for tag in page.get("semantic_tag_keys", []))
        document_index.append(
            {
                "doc_id": doc["doc_id"],
                "source_file_name": doc.get("source_file_name"),
                "region_guess": doc.get("region_guess"),
                "pilot_bucket": doc.get("pilot_bucket"),
                "extension": doc.get("extension"),
                "pdf_kind": doc.get("pdf_kind"),
                "page_count_manifest": doc.get("page_count"),
                "processed_records": len(doc_pages),
                "records_with_text": sum(1 for page in doc_pages if page.get("text_clean")),
                "records_needing_ocr": sum(1 for page in doc_pages if page.get("needs_ocr")),
                "top_semantic_tags": ",".join(tag for tag, _ in tag_counts.most_common(8)),
            }
        )

    write_jsonl(INDEXES_DIR / "pilot_document_index.jsonl", document_index)
    write_jsonl(INDEXES_DIR / "pilot_page_search_index.jsonl", search_pages)
    write_json(INDEXES_DIR / "pilot_tag_index.json", {tag: sorted(doc_ids) for tag, doc_ids in tag_index.items()})

    csv_path = INDEXES_DIR / "pilot_document_index.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = list(document_index[0].keys()) if document_index else []
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in document_index:
            writer.writerow(row)
    print(f"Wrote pilot indexes to {INDEXES_DIR}")


if __name__ == "__main__":
    main()


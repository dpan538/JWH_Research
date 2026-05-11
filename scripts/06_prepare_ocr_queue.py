from __future__ import annotations

from common import METADATA_DIR, read_jsonl, write_json, write_jsonl


def priority_for(row: dict, doc_lookup: dict[str, dict]) -> int:
    doc = doc_lookup.get(row["doc_id"], {})
    if doc.get("is_incomplete_download") or doc.get("is_archive") or doc.get("has_manifest_errors"):
        return 90
    if row.get("source_page_type") == "doc_chunk":
        return 80
    if row.get("image_count", 0):
        return 20
    if "possible_blank_page" in row.get("qc_flags", []):
        return 70
    return 40


def main() -> None:
    inventory = read_jsonl(METADATA_DIR / "page_inventory_pilot.jsonl")
    pilot_docs = read_jsonl(METADATA_DIR / "pilot_documents.jsonl")
    if not inventory:
        raise FileNotFoundError("Run 05_detect_ocr_pages.py first.")

    doc_lookup = {doc["doc_id"]: doc for doc in pilot_docs}
    queue = []
    for row in inventory:
        if not row.get("needs_ocr"):
            continue
        doc = doc_lookup.get(row["doc_id"], {})
        queue.append(
            {
                "doc_id": row["doc_id"],
                "source_file_name": row.get("source_file_name"),
                "source_path_current": doc.get("source_path_current"),
                "page_number": row.get("page_number"),
                "source_page_type": row.get("source_page_type"),
                "priority": priority_for(row, doc_lookup),
                "reason": ",".join(row.get("qc_flags", [])),
                "ocr_status": "queued_not_run",
            }
        )
    queue.sort(key=lambda item: (item["priority"], item["doc_id"], item["page_number"] or 0))
    write_jsonl(METADATA_DIR / "ocr_queue_pilot.jsonl", queue)
    write_json(
        METADATA_DIR / "ocr_queue_pilot_summary.json",
        {
            "queued_page_or_chunk_records": len(queue),
            "note": "Pilot OCR queue only. Full-corpus OCR has not been run.",
        },
    )
    print(f"Queued {len(queue)} pilot records for OCR")


if __name__ == "__main__":
    main()


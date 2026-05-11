from __future__ import annotations

from collections import Counter, defaultdict

from common import METADATA_DIR, QC_DIR, TEXT_RAW_DIR, TEXT_THRESHOLD, counter_to_dict, read_jsonl, write_json, write_jsonl


def classify_page(row: dict) -> dict:
    char_count = row.get("char_count") or 0
    image_count = row.get("image_count")
    flags = set(row.get("qc_flags", []))
    has_text = char_count >= TEXT_THRESHOLD
    needs_ocr = bool(row.get("needs_ocr")) or not has_text
    if char_count == 0 and image_count == 0:
        flags.add("possible_blank_page")
    if char_count > 0 and char_count < TEXT_THRESHOLD:
        flags.add("thin_text_layer")
    if needs_ocr:
        flags.add("needs_ocr")
    return {
        "doc_id": row["doc_id"],
        "source_file_name": row.get("source_file_name"),
        "page_number": row.get("page_number"),
        "source_page_type": row.get("source_page_type"),
        "char_count": char_count,
        "has_existing_text": has_text,
        "needs_ocr": needs_ocr,
        "image_count": image_count,
        "qc_flags": sorted(flags),
    }


def main() -> None:
    rows = read_jsonl(TEXT_RAW_DIR / "pilot_pages_raw.jsonl")
    if not rows:
        raise FileNotFoundError("Run 04_extract_existing_text.py first.")

    inventory = [classify_page(row) for row in rows]
    write_jsonl(METADATA_DIR / "page_inventory_pilot.jsonl", inventory)

    flagged = [row for row in inventory if row["qc_flags"]]
    write_jsonl(QC_DIR / "page_quality_flags_pilot.jsonl", flagged)

    by_doc: dict[str, Counter] = defaultdict(Counter)
    for row in inventory:
        doc_counter = by_doc[row["doc_id"]]
        doc_counter["records"] += 1
        if row["has_existing_text"]:
            doc_counter["records_with_existing_text"] += 1
        if row["needs_ocr"]:
            doc_counter["records_needing_ocr"] += 1
        if "possible_blank_page" in row["qc_flags"]:
            doc_counter["possible_blank_pages"] += 1
        if "thin_text_layer" in row["qc_flags"]:
            doc_counter["thin_text_layer_pages"] += 1

    summary = {
        "page_or_chunk_records": len(inventory),
        "records_with_existing_text": sum(1 for row in inventory if row["has_existing_text"]),
        "records_needing_ocr": sum(1 for row in inventory if row["needs_ocr"]),
        "possible_blank_pages": sum(1 for row in inventory if "possible_blank_page" in row["qc_flags"]),
        "thin_text_layer_pages": sum(1 for row in inventory if "thin_text_layer" in row["qc_flags"]),
        "flag_counts": counter_to_dict(Counter(flag for row in inventory for flag in row["qc_flags"])),
        "by_doc": {doc_id: counter_to_dict(counter) for doc_id, counter in by_doc.items()},
    }
    write_json(METADATA_DIR / "ocr_detection_summary_pilot.json", summary)
    print(f"Detected OCR needs for {len(inventory)} page/chunk records")
    print(f"Records needing OCR: {summary['records_needing_ocr']}")


if __name__ == "__main__":
    main()


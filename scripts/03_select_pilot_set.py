from __future__ import annotations

from collections import Counter

from common import METADATA_DIR, read_jsonl, write_csv, write_json, write_jsonl


TARGET_QUOTAS = {
    "searchable_pdf": 5,
    "partial_text_pdf": 4,
    "scanned_pdf": 5,
    "doc": 4,
    "qc_edge": 2,
}


def bucket_for(doc: dict) -> str:
    name = doc.get("source_file_name", "")
    extension = doc.get("extension")
    if doc.get("is_archive") or doc.get("is_incomplete_download") or doc.get("has_manifest_errors"):
        return "qc_edge"
    if str(name).lower().endswith(".doc") or extension == ".doc":
        return "doc"
    if doc.get("pdf_kind") == "searchable_text_pdf":
        return "searchable_pdf"
    if doc.get("pdf_kind") == "mostly_scanned_with_some_text":
        return "partial_text_pdf"
    if doc.get("pdf_kind") == "scanned_image_pdf_no_text_layer":
        return "scanned_pdf"
    return "other"


def sort_key(doc: dict) -> tuple:
    region_rank = {"江苏": 0, "安徽": 1, "上海": 2, "跨省/综合": 3, "未判定/综合": 4}
    page_count = doc.get("page_count") or 999999
    size_mb = doc.get("size_mb") or 999999
    return (region_rank.get(doc.get("region_guess"), 5), page_count, size_mb, doc.get("source_file_name", ""))


def balanced_take(candidates: list[dict], quota: int) -> list[dict]:
    selected = []
    seen_regions = Counter()
    remaining = sorted(candidates, key=sort_key)
    while remaining and len(selected) < quota:
        remaining.sort(key=lambda doc: (seen_regions[doc.get("region_guess")] * 100000, *sort_key(doc)))
        doc = remaining.pop(0)
        selected.append(doc)
        seen_regions[doc.get("region_guess")] += 1
    return selected


def main() -> None:
    docs = read_jsonl(METADATA_DIR / "documents.jsonl")
    if not docs:
        raise FileNotFoundError("Run 02_generate_doc_ids.py first.")

    by_bucket: dict[str, list[dict]] = {bucket: [] for bucket in TARGET_QUOTAS}
    for doc in docs:
        bucket = bucket_for(doc)
        if bucket in by_bucket:
            by_bucket[bucket].append(doc)

    selected = []
    for bucket, quota in TARGET_QUOTAS.items():
        for doc in balanced_take(by_bucket[bucket], quota):
            pilot = dict(doc)
            pilot["pilot_bucket"] = bucket
            selected.append(pilot)

    selected_ids = {doc["doc_id"] for doc in selected}
    if len(selected) < 20:
        leftovers = [doc for doc in docs if doc["doc_id"] not in selected_ids]
        for doc in sorted(leftovers, key=sort_key):
            pilot = dict(doc)
            pilot["pilot_bucket"] = "backfill"
            selected.append(pilot)
            selected_ids.add(doc["doc_id"])
            if len(selected) == 20:
                break

    selected = selected[:20]
    summary = {
        "pilot_document_count": len(selected),
        "target_quotas": TARGET_QUOTAS,
        "actual_by_bucket": dict(Counter(doc["pilot_bucket"] for doc in selected)),
        "actual_by_region": dict(Counter(doc.get("region_guess") for doc in selected)),
        "selection_policy": "Deterministic balanced pilot: searchable PDF, partial text PDF, scanned PDF, DOC, and QC edge cases.",
    }
    fields = [
        "doc_id",
        "pilot_bucket",
        "source_file_name",
        "region_guess",
        "extension",
        "pdf_kind",
        "page_count",
        "size_mb",
        "is_incomplete_download",
        "is_archive",
        "has_manifest_errors",
    ]
    write_jsonl(METADATA_DIR / "pilot_documents.jsonl", selected)
    write_csv(METADATA_DIR / "pilot_documents.csv", selected, fields)
    write_json(METADATA_DIR / "pilot_selection_summary.json", summary)
    print(f"Selected {len(selected)} pilot documents")
    print(summary)


if __name__ == "__main__":
    main()


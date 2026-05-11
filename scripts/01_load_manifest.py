from __future__ import annotations

from collections import Counter

from common import (
    MANIFEST_DIR,
    SOURCE_MANIFEST_JSON,
    copy_source_manifests,
    counter_to_dict,
    ensure_dirs,
    load_json,
    write_json,
    write_jsonl,
)


def main() -> None:
    ensure_dirs()
    if not SOURCE_MANIFEST_JSON.exists():
        raise FileNotFoundError(f"Missing source manifest: {SOURCE_MANIFEST_JSON}")

    copy_source_manifests()
    source = load_json(SOURCE_MANIFEST_JSON)
    records = source.get("records", [])
    normalized = []

    for ordinal, record in enumerate(records, start=1):
        item = dict(record)
        item["source_ordinal"] = ordinal
        item["source_file_name"] = item.get("file_name", "")
        item["source_path_current"] = item.get("path", "")
        item["manifest_source"] = str(SOURCE_MANIFEST_JSON)
        item["is_incomplete_download"] = ".downloading" in item.get("file_name", "")
        item["is_archive"] = item.get("extension") == ".rar" or item.get("file_name", "").lower().endswith(".rar")
        item["has_manifest_errors"] = bool(item.get("errors"))
        normalized.append(item)

    summary = {
        "source_manifest": str(SOURCE_MANIFEST_JSON),
        "file_count": len(normalized),
        "by_extension": counter_to_dict(Counter(item.get("extension") for item in normalized)),
        "by_region_guess": counter_to_dict(Counter(item.get("region_guess") for item in normalized)),
        "by_pdf_kind": counter_to_dict(Counter(item.get("pdf_kind") for item in normalized if item.get("pdf_kind"))),
        "incomplete_download_count": sum(1 for item in normalized if item["is_incomplete_download"]),
        "archive_count": sum(1 for item in normalized if item["is_archive"]),
        "manifest_error_count": sum(1 for item in normalized if item["has_manifest_errors"]),
    }

    write_jsonl(MANIFEST_DIR / "normalized_manifest.jsonl", normalized)
    write_json(MANIFEST_DIR / "load_manifest_summary.json", summary)
    print(f"Loaded {len(normalized)} records")
    print(f"Wrote {MANIFEST_DIR / 'normalized_manifest.jsonl'}")


if __name__ == "__main__":
    main()


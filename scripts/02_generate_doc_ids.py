from __future__ import annotations

from collections import Counter

from common import MANIFEST_DIR, METADATA_DIR, read_jsonl, stable_doc_id, write_csv, write_json, write_jsonl


def main() -> None:
    records = read_jsonl(MANIFEST_DIR / "normalized_manifest.jsonl")
    if not records:
        raise FileNotFoundError("Run 01_load_manifest.py first.")

    used: Counter[str] = Counter()
    documents = []
    id_map = []

    for record in records:
        base_id = stable_doc_id(record)
        used[base_id] += 1
        doc_id = base_id if used[base_id] == 1 else f"{base_id}_{used[base_id]:02d}"
        metadata = {
            "doc_id": doc_id,
            "source_ordinal": record.get("source_ordinal"),
            "source_file_name": record.get("source_file_name"),
            "source_path_current": record.get("source_path_current"),
            "size_bytes": record.get("size_bytes"),
            "size_mb": record.get("size_mb"),
            "extension": record.get("extension"),
            "region_guess": record.get("region_guess"),
            "period_terms": record.get("period_terms", []),
            "genre_tags": record.get("genre_tags", []),
            "reader": record.get("reader"),
            "read_status": record.get("read_status"),
            "page_count": record.get("page_count"),
            "pdf_kind": record.get("pdf_kind"),
            "text_chars_manifest": record.get("text_chars"),
            "text_pages_manifest": record.get("text_pages"),
            "image_pages_manifest": record.get("image_pages"),
            "outline_count": record.get("outline_count"),
            "is_incomplete_download": record.get("is_incomplete_download", False),
            "is_archive": record.get("is_archive", False),
            "has_manifest_errors": record.get("has_manifest_errors", False),
            "manifest_errors": record.get("errors", []),
            "doc_id_basis": "sha1(normalized source_file_name | size_bytes | page_count)",
        }
        documents.append(metadata)
        id_map.append(
            {
                "doc_id": doc_id,
                "source_file_name": metadata["source_file_name"],
                "source_path_current": metadata["source_path_current"],
                "size_bytes": metadata["size_bytes"],
                "page_count": metadata["page_count"],
                "pdf_kind": metadata["pdf_kind"],
            }
        )

    write_jsonl(METADATA_DIR / "documents.jsonl", documents)
    write_json(METADATA_DIR / "doc_id_map.json", {row["doc_id"]: row for row in id_map})
    write_csv(
        METADATA_DIR / "doc_id_map.csv",
        id_map,
        ["doc_id", "source_file_name", "source_path_current", "size_bytes", "page_count", "pdf_kind"],
    )
    write_json(
        METADATA_DIR / "doc_id_summary.json",
        {
            "document_count": len(documents),
            "unique_doc_id_count": len({item["doc_id"] for item in documents}),
            "collision_count": sum(value - 1 for value in used.values() if value > 1),
        },
    )
    print(f"Generated {len(documents)} doc_id values")
    print(f"Wrote {METADATA_DIR / 'documents.jsonl'}")


if __name__ == "__main__":
    main()


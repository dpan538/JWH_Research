from __future__ import annotations

from collections import Counter, defaultdict

from common import TEXT_ANNOTATED_DIR, TEXT_CLEAN_DIR, semantic_tags_for_text, read_jsonl, write_json, write_jsonl


def main() -> None:
    rows = read_jsonl(TEXT_CLEAN_DIR / "pilot_pages_clean.jsonl")
    if not rows:
        raise FileNotFoundError("Run 08_clean_text.py first.")

    annotated = []
    doc_tag_counts: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        tags = semantic_tags_for_text(row.get("text_clean", ""))
        new_row = dict(row)
        new_row["semantic_tags"] = tags
        new_row["semantic_tag_keys"] = sorted(tags)
        annotated.append(new_row)
        for tag in tags:
            doc_tag_counts[row["doc_id"]][tag] += 1

    by_doc: dict[str, list[dict]] = {}
    for row in annotated:
        by_doc.setdefault(row["doc_id"], []).append(row)

    for doc_id, doc_rows in by_doc.items():
        write_jsonl(TEXT_ANNOTATED_DIR / f"{doc_id}.jsonl", doc_rows)

    summary = {
        doc_id: {"tagged_page_counts": dict(counter), "tag_keys": sorted(counter)}
        for doc_id, counter in doc_tag_counts.items()
    }
    write_jsonl(TEXT_ANNOTATED_DIR / "pilot_pages_annotated.jsonl", annotated)
    write_json(TEXT_ANNOTATED_DIR / "pilot_annotation_summary.json", summary)
    print(f"Annotated {len(annotated)} page/chunk records")


if __name__ == "__main__":
    main()


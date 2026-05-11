from __future__ import annotations

from common import METADATA_DIR, READING_EXPORTS_DIR, TEXT_ANNOTATED_DIR, read_jsonl, safe_filename


def main() -> None:
    rows = read_jsonl(TEXT_ANNOTATED_DIR / "pilot_pages_annotated.jsonl")
    docs = read_jsonl(METADATA_DIR / "pilot_documents.jsonl")
    if not rows or not docs:
        raise FileNotFoundError("Run 09_annotate_entities.py first.")

    by_doc: dict[str, list[dict]] = {}
    for row in rows:
        by_doc.setdefault(row["doc_id"], []).append(row)

    doc_lookup = {doc["doc_id"]: doc for doc in docs}
    written = []
    for doc_id, doc_rows in by_doc.items():
        doc = doc_lookup.get(doc_id, {})
        title = doc.get("source_file_name", doc_id)
        md = []
        md.append("---")
        md.append(f"doc_id: {doc_id}")
        md.append(f"source_file_name: {title}")
        md.append(f"region_guess: {doc.get('region_guess', '')}")
        md.append(f"pdf_kind: {doc.get('pdf_kind', '')}")
        md.append(f"pilot_bucket: {doc.get('pilot_bucket', '')}")
        md.append("---")
        md.append("")
        md.append(f"# {title}")
        md.append("")
        md.append(f"- `doc_id`: `{doc_id}`")
        md.append(f"- 原始路径: `{doc.get('source_path_current', '')}`")
        md.append(f"- 试点类别: `{doc.get('pilot_bucket', '')}`")
        md.append("")
        for row in sorted(doc_rows, key=lambda item: item.get("page_number") or 0):
            page_label = "页" if row.get("source_page_type") == "pdf_page" else "文本块"
            md.append(f"## {page_label} {row.get('page_number')}")
            if row.get("semantic_tag_keys"):
                md.append(f"标签: {', '.join(row.get('semantic_tag_keys', []))}")
                md.append("")
            text = row.get("text_clean", "")
            if text:
                md.append(text)
            elif row.get("needs_ocr"):
                md.append("[需 OCR：此页/块没有可用文字层。]")
            else:
                md.append("[无可读文本。]")
            md.append("")
        filename = f"{doc_id}__{safe_filename(title, 64)}.md"
        path = READING_EXPORTS_DIR / filename
        path.write_text("\n".join(md), encoding="utf-8")
        written.append(str(path))

    (READING_EXPORTS_DIR / "pilot_markdown_exports.txt").write_text("\n".join(written) + "\n", encoding="utf-8")
    print(f"Wrote {len(written)} Markdown reading exports")


if __name__ == "__main__":
    main()


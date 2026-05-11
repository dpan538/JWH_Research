from __future__ import annotations

import re

from common import TEXT_CLEAN_DIR, TEXT_RAW_DIR, clean_whitespace, read_jsonl, write_jsonl


def clean_page_text(text: str) -> str:
    text = clean_whitespace(text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"([。！？；])\s+", r"\1\n", text)
    return text.strip()


def main() -> None:
    rows = read_jsonl(TEXT_RAW_DIR / "pilot_pages_raw.jsonl")
    if not rows:
        raise FileNotFoundError("Run 04_extract_existing_text.py first.")

    cleaned = []
    by_doc: dict[str, list[dict]] = {}
    for row in rows:
        new_row = dict(row)
        new_row["text_clean"] = clean_page_text(row.get("text", ""))
        new_row["clean_char_count"] = len(new_row["text_clean"])
        new_row.pop("text", None)
        cleaned.append(new_row)
        by_doc.setdefault(new_row["doc_id"], []).append(new_row)

    for doc_id, doc_rows in by_doc.items():
        write_jsonl(TEXT_CLEAN_DIR / f"{doc_id}.jsonl", doc_rows)
    write_jsonl(TEXT_CLEAN_DIR / "pilot_pages_clean.jsonl", cleaned)
    print(f"Cleaned {len(cleaned)} page/chunk records")


if __name__ == "__main__":
    main()


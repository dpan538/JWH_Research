from __future__ import annotations

from collections import Counter

from common import (
    METADATA_DIR,
    PROJECT_ROOT,
    QC_DIR,
    TEXT_RAW_DIR,
    counter_to_dict,
    read_jsonl,
    write_json,
)


def main() -> None:
    docs = read_jsonl(METADATA_DIR / "pilot_documents.jsonl")
    pages = read_jsonl(METADATA_DIR / "page_inventory_pilot.jsonl")
    issues = read_jsonl(QC_DIR / "pilot_extraction_issues.jsonl")
    raw_pages = read_jsonl(TEXT_RAW_DIR / "pilot_pages_raw.jsonl")
    if not docs:
        raise FileNotFoundError("Run earlier pipeline scripts first.")

    by_doc_page_counts = Counter(page["doc_id"] for page in pages)
    by_doc_ocr_counts = Counter(page["doc_id"] for page in pages if page.get("needs_ocr"))
    by_doc_text_chars = Counter()
    for page in raw_pages:
        by_doc_text_chars[page["doc_id"]] += page.get("char_count") or 0

    issue_counts = Counter(issue.get("issue_type") for issue in issues)
    flag_counts = Counter(flag for page in pages for flag in page.get("qc_flags", []))
    report = {
        "pilot_document_count": len(docs),
        "page_or_chunk_records": len(pages),
        "records_needing_ocr": sum(1 for page in pages if page.get("needs_ocr")),
        "records_with_existing_text": sum(1 for page in pages if page.get("has_existing_text")),
        "total_existing_text_chars": sum(by_doc_text_chars.values()),
        "issue_counts": counter_to_dict(issue_counts),
        "quality_flag_counts": counter_to_dict(flag_counts),
        "documents": [],
    }
    for doc in docs:
        report["documents"].append(
            {
                "doc_id": doc["doc_id"],
                "source_file_name": doc.get("source_file_name"),
                "pilot_bucket": doc.get("pilot_bucket"),
                "region_guess": doc.get("region_guess"),
                "pdf_kind": doc.get("pdf_kind"),
                "processed_records": by_doc_page_counts[doc["doc_id"]],
                "records_needing_ocr": by_doc_ocr_counts[doc["doc_id"]],
                "existing_text_chars": by_doc_text_chars[doc["doc_id"]],
                "is_incomplete_download": doc.get("is_incomplete_download"),
                "is_archive": doc.get("is_archive"),
                "has_manifest_errors": doc.get("has_manifest_errors"),
            }
        )

    write_json(QC_DIR / "pilot_processing_report.json", report)

    lines = [
        "# 第一轮扫描试点处理报告",
        "",
        f"- 项目目录: `{PROJECT_ROOT}`",
        f"- 试点文档数: {report['pilot_document_count']}",
        f"- 页/文本块记录数: {report['page_or_chunk_records']}",
        f"- 已有文字记录数: {report['records_with_existing_text']}",
        f"- 需 OCR 记录数: {report['records_needing_ocr']}",
        f"- 已抽取文字字符数: {report['total_existing_text_chars']}",
        "",
        "## 质量标记",
        "",
    ]
    for key, value in sorted(report["quality_flag_counts"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 抽取/文件问题", ""])
    if report["issue_counts"]:
        for key, value in sorted(report["issue_counts"].items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- 未记录抽取问题")
    lines.extend(["", "## 试点文档", ""])
    for doc in report["documents"]:
        lines.append(
            f"- `{doc['doc_id']}` {doc['source_file_name']} | {doc['pilot_bucket']} | "
            f"records={doc['processed_records']} | ocr={doc['records_needing_ocr']} | chars={doc['existing_text_chars']}"
        )
    lines.extend(
        [
            "",
            "## 下一步",
            "",
            "1. 人工检查 OCR 队列和 Markdown 阅读稿，确认页面切分与标签是否符合预期。",
            "2. 为 OCR 接入页图渲染和中文 OCR 引擎，只对 `ocr_queue_pilot.jsonl` 中的试点页执行。",
            "3. 试点校验通过后，再按批次扩展到全库，避免一次性处理 245,000 页。",
        ]
    )
    (QC_DIR / "pilot_processing_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {QC_DIR / 'pilot_processing_report.md'}")


if __name__ == "__main__":
    main()


from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from common import INDEXES_DIR, METADATA_DIR, PROJECT_ROOT, QC_DIR, read_jsonl, write_json


REPORTS_DIR = PROJECT_ROOT / "data" / "reports"

INDEX_CONFIG = {
    "place_index": {
        "file_stem": "place_index",
        "entity_field": "place_name",
        "label": "地点",
    },
    "person_index": {
        "file_stem": "person_index",
        "entity_field": "person_name",
        "label": "人物",
    },
    "transport_index": {
        "file_stem": "transport_index",
        "entity_field": "transport_term",
        "label": "交通",
    },
    "dialect_index": {
        "file_stem": "dialect_index",
        "entity_field": "dialect_term",
        "label": "方言",
    },
    "custom_index": {
        "file_stem": "custom_index",
        "entity_field": "custom_term",
        "label": "风俗",
    },
    "relic_index": {
        "file_stem": "relic_index",
        "entity_field": "relic_name",
        "label": "文物/遗迹",
    },
}

DENSITY_COLUMNS = [
    "place_index",
    "person_index",
    "transport_index",
    "dialect_index",
    "custom_index",
    "relic_index",
]

GENERIC_TERMS_BY_INDEX = {
    "place_index": {"府", "州", "县", "镇", "乡", "村", "城", "山", "湖", "河", "港", "桥"},
    "person_index": {"人物", "主编", "委员", "顾问", "主任"},
    "transport_index": {"交通", "道路", "公路", "桥", "车", "船"},
    "dialect_index": {"方言", "俗语", "土语", "声母", "韵母", "声调", "音系"},
    "custom_index": {"风俗", "民俗", "习俗", "岁时", "节令", "风土"},
    "relic_index": {"文物", "古迹", "遗址", "胜迹", "书院", "寺", "庙", "塔", "碑", "墓"},
}

TOC_NOISE_PATTERN = re.compile(r"(目录|第[一二三四五六七八九十百0-9]+[章节卷]|\.{4,}|…{2,}|•{2,})")


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_snippet(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def safe_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def percent(part: int | float, total: int | float) -> float:
    if not total:
        return 0.0
    return round((part / total) * 100, 2)


def doc_title(doc_id: str, doc_lookup: dict[str, dict[str, Any]]) -> str:
    doc = doc_lookup.get(doc_id, {})
    name = doc.get("source_file_name") or "(unknown source)"
    return f"{doc_id}（{name}）"


def top_counter(counter: Counter[str], limit: int = 15) -> list[dict[str, Any]]:
    return [{"term": term, "count": count} for term, count in counter.most_common(limit)]


def summarize_top_docs(
    counts_by_doc: dict[str, Counter[str]],
    category: str,
    doc_lookup: dict[str, dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    rows = []
    for doc_id, counts in counts_by_doc.items():
        count = counts.get(category, 0)
        if count <= 0:
            continue
        rows.append(
            {
                "doc_id": doc_id,
                "source_file_name": doc_lookup.get(doc_id, {}).get("source_file_name", ""),
                "count": count,
            }
        )
    rows.sort(key=lambda item: (-item["count"], item["source_file_name"]))
    return rows[:limit]


def summarize_density(
    pilot_docs: list[dict[str, Any]],
    index_rows: dict[str, list[dict[str, str]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Counter[str]]]:
    counts_by_doc: dict[str, Counter[str]] = defaultdict(Counter)
    for index_name, rows in index_rows.items():
        for row in rows:
            doc_id = row.get("doc_id", "").strip()
            if doc_id:
                counts_by_doc[doc_id][index_name] += 1

    density_rows: list[dict[str, Any]] = []
    for doc in pilot_docs:
        doc_id = doc["doc_id"]
        row: dict[str, Any] = {
            "doc_id": doc_id,
            "source_file_name": doc.get("source_file_name", ""),
            "pilot_bucket": doc.get("pilot_bucket", ""),
            "pdf_kind": doc.get("pdf_kind", ""),
            "region_guess": doc.get("region_guess", ""),
        }
        total = 0
        for category in DENSITY_COLUMNS:
            value = counts_by_doc[doc_id].get(category, 0)
            row[category] = value
            total += value
        row["total_indexed_entries"] = total
        density_rows.append(row)

    top_density = sorted(
        density_rows,
        key=lambda item: (-item["total_indexed_entries"], item["source_file_name"]),
    )[:10]
    return density_rows, top_density, counts_by_doc


def audit_index_quality(index_rows: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    audit: dict[str, Any] = {}
    for index_name, config in INDEX_CONFIG.items():
        rows = index_rows[index_name]
        entity_field = config["entity_field"]
        entity_counts: Counter[str] = Counter()
        generic_counts: Counter[str] = Counter()
        noise_counts: Counter[str] = Counter()
        confidence_counts: Counter[str] = Counter()
        low_or_uncertain_samples = []
        short_context_rows = []
        source_errors = []

        for row_number, row in enumerate(rows, start=2):
            term = (row.get(entity_field) or "").strip()
            snippet = normalize_snippet(row.get("context_snippet", ""))
            confidence = (row.get("confidence") or "").strip() or "unknown"
            confidence_counts[confidence] += 1
            if term:
                entity_counts[term] += 1
            if term in GENERIC_TERMS_BY_INDEX.get(index_name, set()) or len(term) <= 1:
                generic_counts[term or "(blank)"] += 1
            if term in GENERIC_TERMS_BY_INDEX.get(index_name, set()) and TOC_NOISE_PATTERN.search(snippet):
                noise_counts[term] += 1
            if len(snippet) < 25:
                short_context_rows.append(
                    {
                        "row_number": row_number,
                        "entity": term,
                        "doc_id": row.get("doc_id", ""),
                        "page_number": row.get("page_number", ""),
                        "context_snippet": snippet,
                    }
                )
            if confidence not in {"high"} or "uncertain" in json.dumps(row, ensure_ascii=False).lower():
                low_or_uncertain_samples.append(
                    {
                        "row_number": row_number,
                        "entity": term,
                        "doc_id": row.get("doc_id", ""),
                        "page_number": row.get("page_number", ""),
                        "confidence": confidence,
                        "context_snippet": snippet,
                    }
                )
            if not row.get("doc_id") or safe_int(row.get("page_number")) is None or not snippet:
                source_errors.append(
                    {
                        "row_number": row_number,
                        "entity": term,
                        "doc_id": row.get("doc_id", ""),
                        "page_number": row.get("page_number", ""),
                        "context_snippet": snippet,
                    }
                )

        audit[index_name] = {
            "total_rows": len(rows),
            "most_frequent_entities": top_counter(entity_counts),
            "suspiciously_generic_terms": top_counter(generic_counts, 20),
            "possible_category_noise_terms": top_counter(noise_counts, 20),
            "short_context_count": len(short_context_rows),
            "short_context_samples": short_context_rows[:10],
            "confidence_counts": dict(confidence_counts),
            "low_confidence_or_uncertain_count": len(low_or_uncertain_samples),
            "low_confidence_or_uncertain_samples": low_or_uncertain_samples[:10],
            "source_error_count": len(source_errors),
            "source_error_samples": source_errors[:10],
        }
    return audit


def source_traceability(index_rows: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    by_index = {}
    total_rows = 0
    total_malformed = 0
    for index_name, rows in index_rows.items():
        malformed = []
        for row_number, row in enumerate(rows, start=2):
            snippet = normalize_snippet(row.get("context_snippet", ""))
            problems = []
            if not row.get("doc_id"):
                problems.append("missing_doc_id")
            if safe_int(row.get("page_number")) is None:
                problems.append("missing_or_malformed_page_number")
            if not snippet:
                problems.append("missing_context_snippet")
            if problems:
                malformed.append(
                    {
                        "row_number": row_number,
                        "problems": problems,
                        "doc_id": row.get("doc_id", ""),
                        "page_number": row.get("page_number", ""),
                        "context_snippet": snippet,
                    }
                )
        total_rows += len(rows)
        total_malformed += len(malformed)
        by_index[index_name] = {
            "rows": len(rows),
            "malformed_rows": len(malformed),
            "malformed_samples": malformed[:10],
        }
    return {
        "total_rows": total_rows,
        "total_malformed_rows": total_malformed,
        "traceable": total_rows > 0 and total_malformed == 0,
        "by_index": by_index,
    }


def summarize_source_coverage(
    pilot_docs: list[dict[str, Any]],
    processing_report: dict[str, Any],
    index_rows: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    pilot_doc_ids = {doc["doc_id"] for doc in pilot_docs}
    docs_with_any_index = set()
    pages_with_entries = set()
    docs_by_index = {}
    pages_by_index = {}
    for index_name, rows in index_rows.items():
        doc_ids = {row.get("doc_id", "").strip() for row in rows if row.get("doc_id", "").strip()}
        page_keys = {
            (row.get("doc_id", "").strip(), str(row.get("page_number", "")).strip())
            for row in rows
            if row.get("doc_id", "").strip() and str(row.get("page_number", "")).strip()
        }
        docs_with_any_index.update(doc_ids)
        pages_with_entries.update(page_keys)
        docs_by_index[index_name] = {
            "document_count": len(doc_ids),
            "document_coverage_pct": percent(len(doc_ids & pilot_doc_ids), len(pilot_doc_ids)),
        }
        pages_by_index[index_name] = len(page_keys)

    by_bucket: dict[str, dict[str, Any]] = defaultdict(lambda: {"documents": 0, "indexed_entries": 0, "existing_text_records": 0, "processed_records": 0})
    report_docs = {doc.get("doc_id"): doc for doc in processing_report.get("documents", [])}
    for doc in pilot_docs:
        doc_id = doc["doc_id"]
        bucket = doc.get("pilot_bucket") or "unknown"
        by_bucket[bucket]["documents"] += 1
        report_doc = report_docs.get(doc_id, {})
        by_bucket[bucket]["existing_text_records"] += int(report_doc.get("processed_records", 0)) - int(report_doc.get("records_needing_ocr", 0))
        by_bucket[bucket]["processed_records"] += int(report_doc.get("processed_records", 0))
    for rows in index_rows.values():
        for row in rows:
            doc_id = row.get("doc_id")
            doc = next((item for item in pilot_docs if item.get("doc_id") == doc_id), None)
            if doc:
                by_bucket[doc.get("pilot_bucket") or "unknown"]["indexed_entries"] += 1
    for bucket, payload in by_bucket.items():
        payload["text_record_coverage_pct"] = percent(payload["existing_text_records"], payload["processed_records"])
        payload["avg_indexed_entries_per_doc"] = round(payload["indexed_entries"] / payload["documents"], 2) if payload["documents"] else 0

    return {
        "pilot_document_count": len(pilot_docs),
        "documents_with_any_index": len(docs_with_any_index & pilot_doc_ids),
        "documents_without_index_entries": sorted(pilot_doc_ids - docs_with_any_index),
        "document_coverage_pct": percent(len(docs_with_any_index & pilot_doc_ids), len(pilot_doc_ids)),
        "indexed_page_count": len(pages_with_entries),
        "docs_by_index": docs_by_index,
        "pages_by_index": pages_by_index,
        "by_pilot_bucket": dict(sorted(by_bucket.items())),
    }


def summarize_doc_types(
    pilot_docs: list[dict[str, Any]],
    density_rows: list[dict[str, Any]],
    processing_report: dict[str, Any],
) -> list[dict[str, Any]]:
    density_by_doc = {row["doc_id"]: row["total_indexed_entries"] for row in density_rows}
    report_docs = {doc.get("doc_id"): doc for doc in processing_report.get("documents", [])}
    type_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "document_type": "",
            "documents": 0,
            "indexed_entries": 0,
            "processed_records": 0,
            "records_needing_ocr": 0,
            "existing_text_chars": 0,
        }
    )
    for doc in pilot_docs:
        tags = doc.get("genre_tags") or ["未分类"]
        for tag in tags:
            item = type_stats[tag]
            item["document_type"] = tag
            item["documents"] += 1
            item["indexed_entries"] += density_by_doc.get(doc["doc_id"], 0)
            report_doc = report_docs.get(doc["doc_id"], {})
            item["processed_records"] += int(report_doc.get("processed_records", 0))
            item["records_needing_ocr"] += int(report_doc.get("records_needing_ocr", 0))
            item["existing_text_chars"] += int(report_doc.get("existing_text_chars", 0))

    rows = []
    for item in type_stats.values():
        item["avg_indexed_entries_per_doc"] = round(item["indexed_entries"] / item["documents"], 2) if item["documents"] else 0
        item["ocr_need_pct"] = percent(item["records_needing_ocr"], item["processed_records"])
        rows.append(item)
    rows.sort(key=lambda item: (-item["avg_indexed_entries_per_doc"], item["ocr_need_pct"], item["document_type"]))
    return rows


def build_direction_evaluations(
    counts_by_doc: dict[str, Counter[str]],
    doc_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    direction_a_categories = ["place_index", "transport_index", "person_index", "dialect_index"]
    direction_b_categories = ["custom_index", "person_index", "relic_index"]

    direction_a = {
        "strongest_place_documents": summarize_top_docs(counts_by_doc, "place_index", doc_lookup),
        "strongest_transport_documents": summarize_top_docs(counts_by_doc, "transport_index", doc_lookup),
        "strongest_person_documents": summarize_top_docs(counts_by_doc, "person_index", doc_lookup),
        "strongest_dialect_documents": summarize_top_docs(counts_by_doc, "dialect_index", doc_lookup),
        "category_totals": {
            category: sum(counts.get(category, 0) for counts in counts_by_doc.values())
            for category in direction_a_categories
        },
    }
    direction_a["total_entries"] = sum(direction_a["category_totals"].values())
    direction_a["documents_with_any_direction_a_entry"] = sum(
        1 for counts in counts_by_doc.values() if any(counts.get(category, 0) for category in direction_a_categories)
    )

    overlap_rows = []
    for doc_id, counts in counts_by_doc.items():
        if counts.get("person_index", 0) and counts.get("custom_index", 0) and counts.get("relic_index", 0):
            overlap_rows.append(
                {
                    "doc_id": doc_id,
                    "source_file_name": doc_lookup.get(doc_id, {}).get("source_file_name", ""),
                    "person_index": counts.get("person_index", 0),
                    "custom_index": counts.get("custom_index", 0),
                    "relic_index": counts.get("relic_index", 0),
                    "combined_total": counts.get("person_index", 0) + counts.get("custom_index", 0) + counts.get("relic_index", 0),
                }
            )
    overlap_rows.sort(key=lambda item: (-item["combined_total"], item["source_file_name"]))

    direction_b = {
        "strongest_custom_documents": summarize_top_docs(counts_by_doc, "custom_index", doc_lookup),
        "strongest_relic_documents": summarize_top_docs(counts_by_doc, "relic_index", doc_lookup),
        "overlapping_person_custom_relic_documents": overlap_rows[:10],
        "category_totals": {
            category: sum(counts.get(category, 0) for counts in counts_by_doc.values())
            for category in direction_b_categories
        },
    }
    direction_b["total_entries"] = sum(direction_b["category_totals"].values())
    direction_b["documents_with_any_direction_b_entry"] = sum(
        1 for counts in counts_by_doc.values() if any(counts.get(category, 0) for category in direction_b_categories)
    )

    return {"direction_a": direction_a, "direction_b": direction_b}


def format_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "无。\n"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines) + "\n"


def format_doc_rows(rows: list[dict[str, Any]], count_key: str = "count") -> str:
    return format_table(
        ["doc_id", "文件名", "条目数"],
        [[row["doc_id"], row.get("source_file_name", ""), row.get(count_key, 0)] for row in rows],
    )


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    overview = report["pilot_corpus_overview"]
    traceability = report["source_traceability_check"]
    direction_a = report["direction_a_evaluation"]
    direction_b = report["direction_b_evaluation"]
    quality = report["entity_quality_audit"]
    expansion = report["recommended_full_corpus_expansion_strategy"]
    recommendation = report["final_project_direction_recommendation"]

    lines: list[str] = []
    lines.append("# Pilot Value Evaluation Report\n")
    lines.append("本报告只评估 20 篇 pilot 文档的已有文本层与已生成主题索引；未运行全库 OCR，也未改变主题索引抽取逻辑。\n")

    lines.append("## 1. Pilot Corpus Overview\n")
    lines.append(f"- Pilot 文档数：{overview['pilot_document_count']}。")
    text_status = overview["available_text_status"]
    lines.append(
        f"- 页/分块记录：{text_status['page_or_chunk_records']}；已有文本记录 {text_status['records_with_existing_text']} "
        f"({text_status['existing_text_record_pct']}%)；仍需 OCR 记录 {text_status['records_needing_ocr']} "
        f"({text_status['ocr_needed_record_pct']}%)。"
    )
    lines.append(f"- 已有文本字符数：{text_status['total_existing_text_chars']}。")
    lines.append("- 各类索引总量：")
    lines.append(
        format_table(
            ["类别", "条目数", "覆盖文档数", "覆盖页数"],
            [
                [
                    INDEX_CONFIG[name]["label"],
                    overview["total_indexed_entries_by_category"][name],
                    overview["source_coverage"]["docs_by_index"][name]["document_count"],
                    overview["source_coverage"]["pages_by_index"][name],
                ]
                for name in DENSITY_COLUMNS
            ],
        )
    )
    lines.append(
        f"- 来源覆盖：{overview['source_coverage']['documents_with_any_index']} / "
        f"{overview['pilot_document_count']} 篇 pilot 文档至少有一个主题索引条目，覆盖率 "
        f"{overview['source_coverage']['document_coverage_pct']}%。这反映的是当前已有文本层覆盖，并不等同于全 corpus 价值。"
    )
    lines.append("- 按 pilot bucket 的文本与索引覆盖：")
    lines.append(
        format_table(
            ["bucket", "文档数", "索引条目", "平均条目/文档", "已有文本记录覆盖率"],
            [
                [
                    bucket,
                    item["documents"],
                    item["indexed_entries"],
                    item["avg_indexed_entries_per_doc"],
                    f"{item['text_record_coverage_pct']}%",
                ]
                for bucket, item in overview["source_coverage"]["by_pilot_bucket"].items()
            ],
        )
    )

    lines.append("## 2. Index Density by Document\n")
    lines.append("下表列出索引密度最高的 10 篇文档；条目数高通常意味着已有文本层较完整、主题词命中较多，但也可能包含目录页或通用类目词带来的噪音。\n")
    lines.append(
        format_table(
            ["doc_id", "文件名", "地点", "人物", "交通", "方言", "风俗", "文物/遗迹", "总计"],
            [
                [
                    row["doc_id"],
                    row["source_file_name"],
                    row["place_index"],
                    row["person_index"],
                    row["transport_index"],
                    row["dialect_index"],
                    row["custom_index"],
                    row["relic_index"],
                    row["total_indexed_entries"],
                ]
                for row in report["index_density_by_document"]["top_10_highest_density_documents"]
            ],
        )
    )

    lines.append("## 3. Direction A Evaluation: Geography / Transport / People / Dialect\n")
    lines.append("地点抽取最强文档：")
    lines.append(format_doc_rows(direction_a["strongest_place_documents"]))
    lines.append("交通抽取最强文档：")
    lines.append(format_doc_rows(direction_a["strongest_transport_documents"]))
    lines.append("人物抽取最强文档：")
    lines.append(format_doc_rows(direction_a["strongest_person_documents"]))
    lines.append("方言抽取最强文档：")
    lines.append(format_doc_rows(direction_a["strongest_dialect_documents"]))
    lines.append(direction_a["viability_assessment"] + "\n")

    lines.append("## 4. Direction B Evaluation: Customs / People / Relics\n")
    lines.append("风俗抽取最强文档：")
    lines.append(format_doc_rows(direction_b["strongest_custom_documents"]))
    lines.append("文物/遗迹抽取最强文档：")
    lines.append(format_doc_rows(direction_b["strongest_relic_documents"]))
    lines.append("人物 + 风俗 + 文物/遗迹均有命中的重叠文档：")
    lines.append(
        format_table(
            ["doc_id", "文件名", "人物", "风俗", "文物/遗迹", "合计"],
            [
                [
                    row["doc_id"],
                    row["source_file_name"],
                    row["person_index"],
                    row["custom_index"],
                    row["relic_index"],
                    row["combined_total"],
                ]
                for row in direction_b["overlapping_person_custom_relic_documents"]
            ],
        )
    )
    lines.append(direction_b["viability_assessment"] + "\n")

    lines.append("## 5. Entity Quality Audit\n")
    for index_name in DENSITY_COLUMNS:
        item = quality[index_name]
        label = INDEX_CONFIG[index_name]["label"]
        lines.append(f"### {label}\n")
        lines.append(f"- 总条目：{item['total_rows']}；confidence 分布：{item['confidence_counts']}。")
        lines.append(f"- 低置信或不确定样式条目：{item['low_confidence_or_uncertain_count']}；短 context 条目：{item['short_context_count']}。")
        lines.append("- 高频实体：")
        lines.append(
            format_table(
                ["实体", "次数"],
                [[entry["term"], entry["count"]] for entry in item["most_frequent_entities"][:10]],
            )
        )
        if item["suspiciously_generic_terms"]:
            lines.append("- 可能过于通用的词：")
            lines.append(
                format_table(
                    ["词", "次数"],
                    [[entry["term"], entry["count"]] for entry in item["suspiciously_generic_terms"][:10]],
                )
            )
        if item["possible_category_noise_terms"]:
            lines.append("- 可能是类目/目录噪音的词：")
            lines.append(
                format_table(
                    ["词", "次数"],
                    [[entry["term"], entry["count"]] for entry in item["possible_category_noise_terms"][:10]],
                )
            )
        lines.append("")

    lines.append("## 6. Source Traceability Check\n")
    lines.append(
        f"- 索引总行数：{traceability['total_rows']}；缺失或格式异常行：{traceability['total_malformed_rows']}。"
    )
    if traceability["traceable"]:
        lines.append("- 结论：当前主题索引具备来源可追溯性；每条记录均保留 doc_id、page_number 与 context_snippet。")
    else:
        lines.append("- 结论：当前主题索引仍存在来源字段缺失或页码异常，需要先修复后再扩展。")
    lines.append(
        format_table(
            ["索引", "行数", "异常行"],
            [
                [INDEX_CONFIG[name]["label"], traceability["by_index"][name]["rows"], traceability["by_index"][name]["malformed_rows"]]
                for name in DENSITY_COLUMNS
            ],
        )
    )

    lines.append("## 7. Recommended Full-Corpus Expansion Strategy\n")
    lines.append("按文档类型的 pilot 产出排序：")
    lines.append(
        format_table(
            ["文档类型", "文档数", "索引条目", "平均条目/文档", "OCR需求比例"],
            [
                [
                    row["document_type"],
                    row["documents"],
                    row["indexed_entries"],
                    row["avg_indexed_entries_per_doc"],
                    f"{row['ocr_need_pct']}%",
                ]
                for row in expansion["document_type_priority"][:10]
            ],
        )
    )
    for note in expansion["recommendations"]:
        lines.append(f"- {note}")
    lines.append("")

    lines.append("## 8. Final Project Direction Recommendation\n")
    lines.append(f"- 主方向：{recommendation['primary_direction']}。")
    lines.append(f"- 次方向：{recommendation['secondary_direction']}。")
    lines.append(f"- 依据：{recommendation['evidence_summary']}")
    lines.append(f"- 限制：{recommendation['caution']}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_report() -> dict[str, Any]:
    pilot_docs = read_jsonl(METADATA_DIR / "pilot_documents.jsonl")
    doc_lookup = {doc["doc_id"]: doc for doc in pilot_docs}
    processing_report = load_json(QC_DIR / "pilot_processing_report.json", {})
    ocr_summary = load_json(METADATA_DIR / "ocr_detection_summary_pilot.json", {})
    thematic_summary = load_json(INDEXES_DIR / "thematic_index_summary.json", {})
    page_quality_flags = read_jsonl(QC_DIR / "page_quality_flags_pilot.jsonl")
    extraction_issues = read_jsonl(QC_DIR / "pilot_extraction_issues.jsonl")

    index_rows = {
        index_name: load_csv_rows(INDEXES_DIR / f"{config['file_stem']}.csv")
        for index_name, config in INDEX_CONFIG.items()
    }

    density_rows, top_density, counts_by_doc = summarize_density(pilot_docs, index_rows)
    quality_audit = audit_index_quality(index_rows)
    traceability = source_traceability(index_rows)
    source_coverage = summarize_source_coverage(pilot_docs, processing_report, index_rows)
    document_type_priority = summarize_doc_types(pilot_docs, density_rows, processing_report)
    direction_evaluations = build_direction_evaluations(counts_by_doc, doc_lookup)

    text_status = {
        "page_or_chunk_records": int(processing_report.get("page_or_chunk_records", ocr_summary.get("page_or_chunk_records", 0))),
        "records_with_existing_text": int(processing_report.get("records_with_existing_text", ocr_summary.get("records_with_existing_text", 0))),
        "records_needing_ocr": int(processing_report.get("records_needing_ocr", ocr_summary.get("records_needing_ocr", 0))),
        "total_existing_text_chars": int(processing_report.get("total_existing_text_chars", 0)),
        "possible_blank_pages": int(ocr_summary.get("possible_blank_pages", 0)),
        "thin_text_layer_pages": int(ocr_summary.get("thin_text_layer_pages", 0)),
        "quality_flag_counts": processing_report.get("quality_flag_counts", {}),
        "issue_counts": processing_report.get("issue_counts", {}),
        "page_quality_flag_rows": len(page_quality_flags),
        "extraction_issue_rows": len(extraction_issues),
    }
    text_status["existing_text_record_pct"] = percent(text_status["records_with_existing_text"], text_status["page_or_chunk_records"])
    text_status["ocr_needed_record_pct"] = percent(text_status["records_needing_ocr"], text_status["page_or_chunk_records"])

    total_indexed_entries_by_category = {
        index_name: len(rows)
        for index_name, rows in index_rows.items()
    }

    direction_a = direction_evaluations["direction_a"]
    direction_b = direction_evaluations["direction_b"]
    direction_a["viability_assessment"] = (
        "方向 A 在 pilot 中最稳的是地点与交通：地点索引量大，交通也有成体系命中，人物可作为辅助线索。"
        "方言目前条目很少，主要说明已有文本层覆盖不足或方言类文档尚未 OCR，不能单独支撑大规模结论。"
        "因此该方向可行，但应表述为“地理/交通为主，人物与方言为辅助”的阶段性路线。"
    )
    direction_b["viability_assessment"] = (
        "方向 B 有一定基础，尤其人物与文物/遗迹可形成互证；但风俗条目数量明显少于地点类，"
        "文物/遗迹索引中也存在“文物、古迹、书院”等通用词，需要在扩展前继续细化专名识别。"
        "该方向适合作为第二阶段专题线，而不是当前唯一主线。"
    )

    ready_indexes = []
    needs_refinement = []
    for index_name, total in total_indexed_entries_by_category.items():
        audit = quality_audit[index_name]
        low_pct = percent(audit["low_confidence_or_uncertain_count"], total)
        generic_count = sum(entry["count"] for entry in audit["suspiciously_generic_terms"])
        generic_pct = percent(generic_count, total)
        if total >= 100 and low_pct <= 35 and generic_pct <= 40:
            ready_indexes.append(index_name)
        else:
            needs_refinement.append(index_name)

    expansion_recommendations = [
        "优先处理 searchable_text_pdf：pilot 显示此类文档能立刻产出可追溯索引，适合先扩大样本并校验实体规则。",
        "第二阶段处理 partial_text_pdf：先用页级 OCR queue 只补无文本页或薄文本层页，避免整本重跑造成成本失控。",
        "第三阶段处理 scanned_pdf：先按文档类型抽样 OCR，例如方言志、镇志、旧县志各取少量，确认主题产出后再批量扩展。",
        "不要把 scanned PDF 当前低索引量解释为研究价值低；它主要反映尚未 OCR。",
        f"可先扩展的索引：{', '.join(INDEX_CONFIG[name]['label'] for name in ready_indexes) or '暂无'}。",
        f"扩展前建议细化的索引：{', '.join(INDEX_CONFIG[name]['label'] for name in needs_refinement) or '暂无'}。",
    ]

    final_recommendation = {
        "primary_direction": "A. geography / transport / people / dialect",
        "secondary_direction": "B. customs / people / relics",
        "evidence_summary": (
            f"方向 A 当前合计 {direction_a['total_entries']} 条，其中地点 "
            f"{direction_a['category_totals']['place_index']} 条、交通 "
            f"{direction_a['category_totals']['transport_index']} 条、人物 "
            f"{direction_a['category_totals']['person_index']} 条；方向 B 合计 "
            f"{direction_b['total_entries']} 条，其中风俗 "
            f"{direction_b['category_totals']['custom_index']} 条、文物/遗迹 "
            f"{direction_b['category_totals']['relic_index']} 条。方向 A 的证据密度更高，且更适合先做跨文档检索。"
        ),
        "caution": (
            "该结论只来自 pilot 的已有文本层。由于仍有大量页面需要 OCR，尤其 scanned 与 partial-text 文档，"
            "当前报告不能代表全 493 文件 corpus 的最终主题分布。"
        ),
    }

    report = {
        "pilot_corpus_overview": {
            "pilot_document_count": len(pilot_docs),
            "available_text_status": text_status,
            "total_indexed_entries_by_category": total_indexed_entries_by_category,
            "thematic_index_summary_source": thematic_summary,
            "source_coverage": source_coverage,
        },
        "index_density_by_document": {
            "documents": density_rows,
            "top_10_highest_density_documents": top_density,
        },
        "direction_a_evaluation": direction_a,
        "direction_b_evaluation": direction_b,
        "entity_quality_audit": quality_audit,
        "source_traceability_check": traceability,
        "recommended_full_corpus_expansion_strategy": {
            "document_type_priority": document_type_priority,
            "ready_indexes_for_expansion": ready_indexes,
            "indexes_needing_refinement_first": needs_refinement,
            "recommendations": expansion_recommendations,
        },
        "final_project_direction_recommendation": final_recommendation,
    }
    return report


def main() -> None:
    report = build_report()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(REPORTS_DIR / "pilot_value_report.json", report)
    write_markdown_report(report, REPORTS_DIR / "pilot_value_report.md")
    print(
        json.dumps(
            {
                "pilot_value_report_md": str(REPORTS_DIR / "pilot_value_report.md"),
                "pilot_value_report_json": str(REPORTS_DIR / "pilot_value_report.json"),
                "pilot_documents": report["pilot_corpus_overview"]["pilot_document_count"],
                "total_indexed_entries": sum(report["pilot_corpus_overview"]["total_indexed_entries_by_category"].values()),
                "source_traceable": report["source_traceability_check"]["traceable"],
                "primary_direction": report["final_project_direction_recommendation"]["primary_direction"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import csv
import random
import re
from pathlib import Path
from typing import Any

from common import INDEXES_DIR, METADATA_DIR, QC_DIR, read_jsonl


RANDOM_SEED = 20260511
SAMPLE_SIZE = 30
AUDIT_DIR = QC_DIR / "sample_audit"

INDEX_SPECS = {
    "place_index": {
        "csv": "place_index.csv",
        "output": "place_index_sample_audit.md",
        "term_field": "place_name",
        "category_fields": ["province", "county_or_city"],
        "label": "Place Index",
    },
    "person_index": {
        "csv": "person_index.csv",
        "output": "person_index_sample_audit.md",
        "term_field": "person_name",
        "category_fields": ["role_or_category", "dynasty_or_period"],
        "label": "Person Index",
    },
    "transport_index": {
        "csv": "transport_index.csv",
        "output": "transport_index_sample_audit.md",
        "term_field": "transport_term",
        "category_fields": ["category", "related_places"],
        "label": "Transport Index",
    },
    "dialect_index": {
        "csv": "dialect_index.csv",
        "output": "dialect_index_sample_audit.md",
        "term_field": "dialect_term",
        "category_fields": ["place"],
        "label": "Dialect Index",
    },
    "custom_index": {
        "csv": "custom_index.csv",
        "output": "custom_index_sample_audit.md",
        "term_field": "custom_term",
        "category_fields": ["category", "place", "date_or_period"],
        "label": "Custom Index",
    },
    "relic_index": {
        "csv": "relic_index.csv",
        "output": "relic_index_sample_audit.md",
        "term_field": "relic_name",
        "category_fields": ["relic_type", "place", "date_or_period"],
        "label": "Relic Index",
    },
}


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def load_doc_lookup() -> dict[str, dict[str, Any]]:
    rows = read_jsonl(METADATA_DIR / "pilot_documents.jsonl")
    if not rows:
        rows = read_jsonl(METADATA_DIR / "documents.jsonl")
    return {row.get("doc_id", ""): row for row in rows if row.get("doc_id")}


def category_summary(row: dict[str, str], fields: list[str]) -> str:
    parts = []
    for field in fields:
        value = normalize_space(row.get(field, ""))
        if value:
            parts.append(f"{field}: {value}")
    return "; ".join(parts)


def sample_rows(index_name: str, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            normalize_space(row.get("doc_id")),
            normalize_space(row.get("page_number")),
            normalize_space(row.get("entity_id")),
            normalize_space(row.get("context_snippet")),
        ),
    )
    rng = random.Random(f"{RANDOM_SEED}:{index_name}")
    if len(ordered_rows) <= SAMPLE_SIZE:
        return ordered_rows
    return rng.sample(ordered_rows, SAMPLE_SIZE)


def write_audit_sheet(
    index_name: str,
    spec: dict[str, Any],
    sampled_rows: list[dict[str, str]],
    total_rows: int,
    doc_lookup: dict[str, dict[str, Any]],
) -> None:
    lines: list[str] = []
    lines.append(f"# {spec['label']} Sample Audit\n")
    lines.append(f"- Index name: `{index_name}`")
    lines.append(f"- Source CSV: `data/indexes/{spec['csv']}`")
    lines.append(f"- Sampling seed: `{RANDOM_SEED}`")
    lines.append(f"- Requested sample size: {SAMPLE_SIZE}")
    lines.append(f"- Actual sampled entries: {len(sampled_rows)}")
    lines.append(f"- Total index entries: {total_rows}\n")
    if len(sampled_rows) < SAMPLE_SIZE:
        lines.append(
            "Note: this index has fewer than 30 available entries, so the audit sheet includes all available rows.\n"
        )

    for number, row in enumerate(sampled_rows, start=1):
        doc_id = normalize_space(row.get("doc_id"))
        doc = doc_lookup.get(doc_id, {})
        filename = normalize_space(doc.get("source_file_name") or row.get("source_file_name") or "")
        term = normalize_space(row.get(spec["term_field"], ""))
        category = category_summary(row, spec["category_fields"])
        snippet = normalize_space(row.get("context_snippet", ""))
        confidence = normalize_space(row.get("confidence", ""))

        lines.append(f"## Sample {number}\n")
        lines.append(f"- index name: `{index_name}`")
        lines.append(f"- entity term: {term}")
        lines.append(f"- doc_id: `{doc_id}`")
        lines.append(f"- original filename: {filename or '(not available)'}")
        lines.append(f"- page_number: {normalize_space(row.get('page_number', ''))}")
        lines.append(f"- confidence: {confidence or '(not available)'}")
        lines.append(f"- category: {category or '(not available)'}")
        lines.append("- context_snippet:")
        lines.append("")
        lines.append(f"> {snippet or '(empty)'}")
        lines.append("")
        lines.append("Manual judgement:")
        lines.append("- correct entity? [yes / no / uncertain]")
        lines.append("- correct category? [yes / no / uncertain]")
        lines.append("- useful context? [yes / no / uncertain]")
        lines.append("- should keep for future full-corpus extraction? [yes / no / uncertain]")
        lines.append("- notes:")
        lines.append("")

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / spec["output"]).write_text("\n".join(lines), encoding="utf-8")


def write_overview(sample_counts: dict[str, dict[str, int]]) -> None:
    lines: list[str] = []
    lines.append("# Sample Audit Overview\n")
    lines.append("这个 audit pack 用于人工抽查六个主题索引的准确性。它不会改变任何抽取规则，也不会运行 OCR；它只是把现有索引中的样本整理成便于人工判断的表单。\n")
    lines.append("## How to Use\n")
    lines.append("1. 逐个打开下面六个 sample audit 文件。")
    lines.append("2. 对每条样本查看实体词、页码、原文件名和 context_snippet。")
    lines.append("3. 在 `Manual judgement` 下填写 yes / no / uncertain。")
    lines.append("4. 如果实体本身正确但类别过粗或上下文来自目录页，请在 notes 里说明。")
    lines.append("5. 审完后，把 no / uncertain 的模式汇总，优先修正会影响全库扩展的规则。\n")
    lines.append("## Why This Matters Before Full-Corpus OCR Expansion\n")
    lines.append("Pilot 索引目前已经具备来源追溯，但自动抽取仍可能包含三类问题：通用词被当作实体、目录页造成类目噪音、以及 OCR/文本层残留导致上下文不完整。")
    lines.append("在投入 full-corpus OCR 之前，人工样本审计可以判断哪些索引规则已经足够稳定，哪些规则需要先收紧。这样可以避免把 OCR 成本花在会放大噪音的抽取流程上。\n")
    lines.append("## Sample Files\n")
    lines.append("| Index | Total entries | Sampled entries | Audit sheet |")
    lines.append("| --- | ---: | ---: | --- |")
    for index_name, spec in INDEX_SPECS.items():
        counts = sample_counts[index_name]
        lines.append(
            f"| `{index_name}` | {counts['total_rows']} | {counts['sampled_rows']} | `{spec['output']}` |"
        )
    lines.append("")
    lines.append(f"Sampling is reproducible with fixed seed `{RANDOM_SEED}`. If an index has fewer than 30 rows, all rows are included.")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "sample_audit_overview.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    doc_lookup = load_doc_lookup()
    sample_counts: dict[str, dict[str, int]] = {}
    for index_name, spec in INDEX_SPECS.items():
        rows = load_csv_rows(INDEXES_DIR / spec["csv"])
        sampled = sample_rows(index_name, rows)
        write_audit_sheet(index_name, spec, sampled, len(rows), doc_lookup)
        sample_counts[index_name] = {"total_rows": len(rows), "sampled_rows": len(sampled)}

    write_overview(sample_counts)
    print("Sample audit pack generated:")
    for path in sorted(AUDIT_DIR.glob("*.md")):
        print(path)


if __name__ == "__main__":
    main()

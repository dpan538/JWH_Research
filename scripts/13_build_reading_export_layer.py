from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from common import (
    METADATA_DIR,
    QC_DIR,
    READING_EXPORTS_DIR,
    TEXT_CLEAN_DIR,
    TEXT_RAW_DIR,
    clean_whitespace,
    read_jsonl,
    safe_filename,
    write_json,
)


OUTPUT_ROOT = READING_EXPORTS_DIR / "documents"

TAG_ORDER = [
    "PLACE",
    "PERSON",
    "DATE",
    "OFFICE",
    "TRANSPORT",
    "DIALECT",
    "CUSTOM",
    "RELIC",
    "INDUSTRY",
    "TAX",
    "EDUCATION",
]

KNOWN_PLACES = [
    "江苏", "安徽", "上海", "苏州", "南京", "金陵", "江宁", "无锡", "常熟", "太仓", "吴县", "吴江",
    "昆山", "盛泽", "镇江", "扬州", "泰州", "盐城", "阜宁", "兴化", "南通", "海安", "连云港",
    "徐州", "淮安", "来安", "岳西", "歙县", "徽州", "安庆", "枞阳", "静安", "嘉定", "青浦",
    "松江", "南汇", "川沙", "盛泽镇", "来安县", "阜宁县", "兴化县", "嘉定县", "静安区",
]

OFFICE_TERMS = [
    "县署", "府署", "州署", "衙署", "知县", "知府", "知州", "县政府", "区政府", "地方志办公室",
    "地方志编纂委员会", "委员会", "公所", "民政局", "财政局", "教育局", "交通局", "公安局",
]

TRANSPORT_TERMS = [
    "交通", "道路", "公路", "铁路", "航运", "民航", "运河", "桥梁", "码头", "渡口", "驿站",
    "客运", "货运", "道路运输", "京杭运河",
]

DIALECT_TERMS = ["方言", "土语", "俗语", "音系", "声母", "韵母", "声调", "吴语", "江淮官话"]
CUSTOM_TERMS = ["风俗", "民俗", "岁时", "节令", "婚丧", "祭祀", "庙会", "习俗", "风土"]
RELIC_TERMS = ["文物", "古迹", "遗址", "碑", "墓", "寺", "塔", "祠", "庙", "书院", "胜迹", "文化遗产"]
INDUSTRY_TERMS = ["工业", "农业", "商业", "手工业", "纺织", "陶瓷", "冶金", "盐业", "粮食", "工厂", "土壤"]
TAX_TERMS = ["赋", "税", "税务", "田赋", "漕", "盐课", "厘金", "财政", "钱粮"]
EDUCATION_TERMS = ["教育", "学校", "书院", "学堂", "小学", "中学", "师范", "科举", "儒学"]

DATE_PATTERN = re.compile(
    r"(?:公元)?(?:1[0-9]{3}|20[0-9]{2})年?|"
    r"(?:民国|弘治|嘉靖|万历|崇祯|康熙|雍正|乾隆|嘉庆|道光|咸丰|同治|光绪|宣统)"
    r"[一二三四五六七八九十百元0-9]{0,6}年?|"
    r"(?:宋代|元代|明代|清代|清朝|明清|清末|清初)"
)

PERSON_LABEL_PATTERN = re.compile(
    r"(?:顾问|主修|主编|编纂|纂修|修订|作者|主任|副主任|委员)\s*[：: ]\s*"
    r"([\u4e00-\u9fff、，, 　]{2,80})"
)


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def page_marker(doc_id: str, page_number: Any, source_file_name: str) -> str:
    return f"[doc_id: {doc_id} | page: {page_number} | source: {source_file_name}]"


def export_clean_text(text: str) -> str:
    text = text or ""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u3000", " ")
    raw_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    heading_re = re.compile(r"^(?:目录|目 录|凡例|序|前言|概述|总述|大事记|第[一二三四五六七八九十百0-9]+[卷编章节目].*)$")
    out: list[str] = []

    def should_join(previous: str, current: str) -> bool:
        if not previous or not current:
            return False
        if len(previous) <= 10 or len(current) <= 6:
            return False
        if heading_re.match(previous) or heading_re.match(current):
            return False
        if previous.endswith(("。", "！", "？", "；", "：")):
            return False
        if re.search(r"[.·…]{3,}", previous) or re.search(r"[.·…]{3,}", current):
            return False
        if re.search(r"[\u4e00-\u9fff，、；：]$", previous) and re.search(r"^[\u4e00-\u9fff“《（0-9]", current):
            return True
        if re.search(r"[A-Za-z0-9]$", previous) and re.search(r"^[A-Za-z0-9]", current):
            return True
        return False

    for line in raw_lines:
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        if out and should_join(out[-1], line):
            out[-1] = out[-1] + line
        else:
            out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def terms_to_patterns(tag: str, terms: list[str], uncertain: bool = False) -> list[dict[str, Any]]:
    patterns = []
    for term in sorted(set(terms), key=len, reverse=True):
        if len(term) < 2:
            continue
        patterns.append({"tag": tag, "pattern": re.compile(re.escape(term)), "uncertain": uncertain, "term": term})
    return patterns


def extract_doc_places(doc: dict[str, Any]) -> list[str]:
    places = list(KNOWN_PLACES)
    filename = doc.get("source_file_name", "")
    for match in re.findall(r"([\u4e00-\u9fff]{2,8}(?:省|市|府|州|县|区|镇|乡))", filename):
        places.append(match)
    region = doc.get("region_guess")
    if region and region not in {"跨省/综合", "未判定/综合"}:
        places.append(region)
    return sorted(set(places), key=len, reverse=True)


def extract_person_candidates(text: str) -> list[str]:
    names: list[str] = []
    for match in PERSON_LABEL_PATTERN.finditer(text[:20000]):
        segment = match.group(1)
        segment = re.sub(r"[^\u4e00-\u9fff、，, ]", " ", segment)
        for item in re.split(r"[、，, ]+", segment):
            item = item.strip()
            if 2 <= len(item) <= 4 and item not in {"主任", "委员", "地方", "办公室", "人民", "政府", "书影", "目录"}:
                names.append(item)
    for match in re.findall(r"（清）([\u4e00-\u9fff]{2,4})(?:纂修|修订|主编|编)", text[:10000]):
        names.append(match)
    return sorted(set(names), key=len, reverse=True)[:80]


def build_annotation_patterns(doc: dict[str, Any], all_text: str) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    patterns += terms_to_patterns("PLACE", extract_doc_places(doc))
    patterns += terms_to_patterns("PERSON", extract_person_candidates(all_text))
    patterns += [{"tag": "DATE", "pattern": DATE_PATTERN, "uncertain": False, "term": "date_pattern"}]
    patterns += terms_to_patterns("OFFICE", OFFICE_TERMS)
    patterns += terms_to_patterns("TRANSPORT", TRANSPORT_TERMS)
    patterns += terms_to_patterns("DIALECT", DIALECT_TERMS)
    patterns += terms_to_patterns("CUSTOM", CUSTOM_TERMS)
    patterns += terms_to_patterns("RELIC", RELIC_TERMS)
    patterns += terms_to_patterns("INDUSTRY", INDUSTRY_TERMS)
    patterns += terms_to_patterns("TAX", TAX_TERMS)
    patterns += terms_to_patterns("EDUCATION", EDUCATION_TERMS)
    return patterns


def annotate_text(text: str, patterns: list[dict[str, Any]]) -> str:
    if not text:
        return ""
    spans: list[tuple[int, int, str, bool]] = []
    occupied = [False] * len(text)
    tag_rank = {tag: idx for idx, tag in enumerate(TAG_ORDER)}

    matches: list[tuple[int, int, str, bool, int]] = []
    for item in patterns:
        for match in item["pattern"].finditer(text):
            start, end = match.span()
            if start == end:
                continue
            matched_text = text[start:end]
            if len(matched_text.strip()) < 2 and item["tag"] != "DATE":
                continue
            matches.append((start, end, item["tag"], item["uncertain"], tag_rank.get(item["tag"], 99)))

    matches.sort(key=lambda span: (span[0], -(span[1] - span[0]), span[4]))
    for start, end, tag, uncertain, _ in matches:
        if any(occupied[start:end]):
            continue
        for idx in range(start, end):
            occupied[idx] = True
        spans.append((start, end, tag, uncertain))

    spans.sort()
    pieces: list[str] = []
    last = 0
    for start, end, tag, uncertain in spans:
        pieces.append(text[last:start])
        attr = ' uncertain="true"' if uncertain else ""
        pieces.append(f"<{tag}{attr}>{text[start:end]}</{tag}>")
        last = end
    pieces.append(text[last:])
    return "".join(pieces)


def collect_by_doc(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["doc_id"]].append(row)
    for doc_rows in grouped.values():
        doc_rows.sort(key=lambda item: item.get("page_number") or 0)
    return grouped


def detect_toc(page_rows: list[dict[str, Any]]) -> list[str]:
    toc_lines: list[str] = []
    for row in page_rows[:30]:
        text = row.get("text_clean") or row.get("text") or ""
        if "目录" not in text and "目 录" not in text:
            continue
        for line in text.splitlines():
            line = clean_whitespace(line)
            if not line:
                continue
            if "目录" in line or re.search(r"第[一二三四五六七八九十百0-9]+[卷编章节目]", line):
                toc_lines.append(line[:160])
            if len(toc_lines) >= 40:
                return toc_lines
    return toc_lines


def detect_major_sections(page_rows: list[dict[str, Any]]) -> list[str]:
    sections: list[str] = []
    seen = set()
    heading_re = re.compile(
        r"^(?:第[一二三四五六七八九十百0-9]+[卷编章节目][^\n]{0,40}|"
        r"卷[一二三四五六七八九十百0-9]+[^\n]{0,30}|"
        r"凡例|序|前言|概述|总述|大事记|目录|地理|建置|交通|教育|人物|艺文|风俗|方言|文物|财政|税务|工业|农业|商业)$"
    )
    for row in page_rows:
        text = row.get("text_clean") or row.get("text") or ""
        for line in text.splitlines():
            line = clean_whitespace(re.sub(r"[.·…]{2,}.*$", "", line))
            if not line or len(line) > 60:
                continue
            if heading_re.search(line) and line not in seen:
                seen.add(line)
                sections.append(line)
                if len(sections) >= 60:
                    return sections
    return sections


def notable_terms(text: str, terms: list[str], limit: int = 30) -> list[str]:
    counts = Counter()
    for term in terms:
        if len(term) < 2:
            continue
        count = text.count(term)
        if count:
            counts[term] = count
    return [term for term, _ in counts.most_common(limit)]


def notable_dates(text: str, limit: int = 30) -> list[str]:
    return [term for term, _ in Counter(DATE_PATTERN.findall(text)).most_common(limit)]


def notable_persons(text: str, limit: int = 30) -> list[str]:
    candidates = extract_person_candidates(text)
    return candidates[:limit]


def quality_warnings(doc: dict[str, Any], inventory_rows: list[dict[str, Any]], extraction_issues: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if doc.get("is_incomplete_download"):
        warnings.append("Source filename indicates an incomplete download.")
    if doc.get("is_archive"):
        warnings.append("Source is an archive; text extraction was not performed in this stage.")
    if doc.get("has_manifest_errors"):
        warnings.append("Source manifest recorded errors.")

    flag_counts = Counter(flag for row in inventory_rows for flag in row.get("qc_flags", []))
    for flag, count in flag_counts.most_common():
        warnings.append(f"{flag}: {count} page/chunk records")

    for issue in extraction_issues:
        warnings.append(f"{issue.get('issue_type')}: {issue.get('message', '')[:180]}")
    if not inventory_rows:
        warnings.append("No page/chunk text records were produced for this document.")
    return warnings


def write_raw_text(path: Path, doc: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [f"# raw_text: {doc['source_file_name']}", ""]
    if not rows:
        lines.extend(["[no page/chunk text records produced]", ""])
    for row in rows:
        lines.append(page_marker(doc["doc_id"], row.get("page_number"), doc["source_file_name"]))
        lines.append("")
        text = row.get("text") or ""
        lines.append(text if text else "[no extracted text; OCR required or source unreadable]")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_clean_text(path: Path, doc: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [f"# clean_reading: {doc['source_file_name']}", ""]
    if not rows:
        lines.extend(["[no page/chunk text records produced]", ""])
    for row in rows:
        lines.append(page_marker(doc["doc_id"], row.get("page_number"), doc["source_file_name"]))
        lines.append("")
        text = export_clean_text(row.get("text_clean") or "")
        lines.append(text if text else "[no readable text; OCR required or source unreadable]")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_annotated_text(path: Path, doc: dict[str, Any], rows: list[dict[str, Any]], patterns: list[dict[str, Any]]) -> None:
    lines = [f"# annotated_reading: {doc['source_file_name']}", ""]
    if not rows:
        lines.extend(["[no page/chunk text records produced]", ""])
    for row in rows:
        lines.append(page_marker(doc["doc_id"], row.get("page_number"), doc["source_file_name"]))
        lines.append("")
        text = export_clean_text(row.get("text_clean") or "")
        annotated = annotate_text(text, patterns)
        lines.append(annotated if annotated else "[no readable text; OCR required or source unreadable]")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_summary(
    path: Path,
    doc: dict[str, Any],
    clean_rows: list[dict[str, Any]],
    inventory_rows: list[dict[str, Any]],
    extraction_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    all_text = "\n".join(row.get("text_clean") or "" for row in clean_rows)
    places = notable_terms(all_text, extract_doc_places(doc))
    persons = notable_persons(all_text)
    warnings = quality_warnings(doc, inventory_rows, extraction_issues)
    text_records = len(clean_rows)
    records_with_text = sum(1 for row in clean_rows if row.get("text_clean"))
    records_needing_ocr = sum(1 for row in inventory_rows if row.get("needs_ocr"))
    page_count = doc.get("page_count") or text_records
    ocr_status = (
        f"{records_with_text}/{text_records} page/chunk records have existing text; "
        f"{records_needing_ocr} require OCR."
    )
    toc = detect_toc(clean_rows)
    sections = detect_major_sections(clean_rows)

    summary = {
        "doc_id": doc["doc_id"],
        "source_file_name": doc.get("source_file_name"),
        "region": doc.get("region_guess"),
        "period": doc.get("period_terms") or [],
        "gazetteer_type": doc.get("genre_tags") or [],
        "page_count": page_count,
        "ocr_text_status": ocr_status,
        "detected_table_of_contents": toc,
        "major_sections": sections,
        "notable_place_names": places,
        "notable_person_names": persons,
        "notable_transport_references": notable_terms(all_text, TRANSPORT_TERMS),
        "notable_dialect_references": notable_terms(all_text, DIALECT_TERMS),
        "notable_custom_folk_references": notable_terms(all_text, CUSTOM_TERMS),
        "notable_relic_cultural_heritage_references": notable_terms(all_text, RELIC_TERMS),
        "quality_warnings": warnings,
    }

    def bullet_list(items: list[str], empty: str = "Not detected") -> list[str]:
        if not items:
            return [f"- {empty}"]
        return [f"- {item}" for item in items]

    lines = [
        f"# summary: {doc.get('source_file_name')}",
        "",
        f"- original filename: `{doc.get('source_file_name')}`",
        f"- doc_id: `{doc['doc_id']}`",
        f"- region: {doc.get('region_guess') or 'Unknown'}",
        f"- period: {', '.join(doc.get('period_terms') or []) or 'Not detected'}",
        f"- type of gazetteer: {', '.join(doc.get('genre_tags') or []) or 'Not detected'}",
        f"- page count: {page_count}",
        f"- OCR/text status: {ocr_status}",
        "",
        "## Detected Table Of Contents",
        "",
        *bullet_list(toc[:40]),
        "",
        "## Major Sections",
        "",
        *bullet_list(sections[:60]),
        "",
        "## Notable Place Names",
        "",
        *bullet_list(places),
        "",
        "## Notable Person Names",
        "",
        *bullet_list(persons),
        "",
        "## Notable Transport References",
        "",
        *bullet_list(summary["notable_transport_references"]),
        "",
        "## Notable Dialect References",
        "",
        *bullet_list(summary["notable_dialect_references"]),
        "",
        "## Notable Custom/Folk References",
        "",
        *bullet_list(summary["notable_custom_folk_references"]),
        "",
        "## Notable Relic/Cultural Heritage References",
        "",
        *bullet_list(summary["notable_relic_cultural_heritage_references"]),
        "",
        "## Quality Warnings",
        "",
        *bullet_list(warnings, "No quality warnings"),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return summary


def main() -> None:
    docs = read_jsonl(METADATA_DIR / "pilot_documents.jsonl")
    raw_rows = collect_by_doc(read_jsonl(TEXT_RAW_DIR / "pilot_pages_raw.jsonl"))
    clean_rows = collect_by_doc(read_jsonl(TEXT_CLEAN_DIR / "pilot_pages_clean.jsonl"))
    inventory_rows = collect_by_doc(read_jsonl(METADATA_DIR / "page_inventory_pilot.jsonl"))
    extraction_issues_by_doc = collect_by_doc(read_jsonl(QC_DIR / "pilot_extraction_issues.jsonl"))

    if not docs:
        raise FileNotFoundError("No pilot documents found. Run scripts/03_select_pilot_set.py first.")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = []
    summaries = []
    for doc in docs:
        doc_id = doc["doc_id"]
        doc_dir = OUTPUT_ROOT / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        raw_doc_rows = raw_rows.get(doc_id, [])
        clean_doc_rows = clean_rows.get(doc_id, [])
        inventory_doc_rows = inventory_rows.get(doc_id, [])
        issues = extraction_issues_by_doc.get(doc_id, [])
        all_text = "\n".join(row.get("text_clean") or "" for row in clean_doc_rows)
        patterns = build_annotation_patterns(doc, all_text)

        write_raw_text(doc_dir / "raw_text.md", doc, raw_doc_rows)
        write_clean_text(doc_dir / "clean_reading.md", doc, clean_doc_rows)
        write_annotated_text(doc_dir / "annotated_reading.md", doc, clean_doc_rows, patterns)
        summary = write_summary(doc_dir / "summary.md", doc, clean_doc_rows, inventory_doc_rows, issues)
        summaries.append(summary)
        manifest.append(
            {
                "doc_id": doc_id,
                "source_file_name": doc.get("source_file_name"),
                "directory": str(doc_dir.relative_to(READING_EXPORTS_DIR)),
                "raw_text": str((doc_dir / "raw_text.md").relative_to(READING_EXPORTS_DIR)),
                "clean_reading": str((doc_dir / "clean_reading.md").relative_to(READING_EXPORTS_DIR)),
                "annotated_reading": str((doc_dir / "annotated_reading.md").relative_to(READING_EXPORTS_DIR)),
                "summary": str((doc_dir / "summary.md").relative_to(READING_EXPORTS_DIR)),
            }
        )

    write_json(READING_EXPORTS_DIR / "reading_export_manifest.json", manifest)
    write_json(READING_EXPORTS_DIR / "document_summaries.json", summaries)
    print(f"Built reading export layer for {len(docs)} documents")
    print(f"Wrote {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()

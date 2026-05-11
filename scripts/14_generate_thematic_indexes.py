from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from common import INDEXES_DIR, METADATA_DIR, TEXT_CLEAN_DIR, REGION_KEYWORDS, read_jsonl, write_json, write_jsonl


MAX_OCCURRENCES_PER_DOC_TERM = 5
SNIPPET_RADIUS = 55

PLACE_EXTRA = [
    "盛泽镇", "来安县", "阜宁县", "岳西县", "兴化县", "嘉定县", "静安区", "吴江县",
    "滁州", "庐州府", "徽州府", "宁国府", "凤台县", "和州", "益阳", "台湾",
]

TRANSPORT_CATEGORIES = {
    "公路": "road",
    "道路": "road",
    "道路运输": "road",
    "铁路": "rail",
    "运河": "waterway",
    "京杭运河": "waterway",
    "航运": "waterway",
    "民航": "aviation",
    "码头": "waterway",
    "渡口": "waterway",
    "桥梁": "bridge",
    "桥": "bridge",
    "驿站": "postal/relay",
    "客运": "passenger_transport",
    "货运": "freight_transport",
    "交通": "general_transport",
}

DIALECT_TERMS = ["方言", "土语", "俗语", "音系", "声母", "韵母", "声调", "吴语", "江淮官话"]

CUSTOM_CATEGORIES = {
    "风俗": "general_custom",
    "民俗": "folk_custom",
    "岁时": "seasonal_custom",
    "节令": "seasonal_custom",
    "婚丧": "life_cycle",
    "祭祀": "ritual",
    "庙会": "temple_fair",
    "习俗": "general_custom",
    "风土": "local_conditions",
}

RELIC_TYPES = {
    "文物": "relic",
    "古迹": "historic_site",
    "遗址": "site",
    "碑": "inscription",
    "墓": "tomb",
    "寺": "temple",
    "塔": "pagoda",
    "祠": "ancestral_hall",
    "庙": "temple",
    "书院": "academy",
    "胜迹": "historic_scenery",
    "文化遗产": "cultural_heritage",
}

PERIOD_PATTERN = re.compile(
    r"(?:公元)?(?:1[0-9]{3}|20[0-9]{2})年?|"
    r"(?:宋代|元代|明代|清代|清朝|明清|清末|清初|民国|弘治|嘉靖|万历|崇祯|康熙|雍正|乾隆|嘉庆|道光|咸丰|同治|光绪|宣统)"
    r"[一二三四五六七八九十百元0-9]{0,6}年?"
)

PERSON_LINE_PATTERN = re.compile(
    r"(?P<label>顾\s*问|主\s*修|副\s*主\s*编|主\s*编|编纂|纂修|修订|作者|主\s*任|副主任|副\s*主任|委\s*员|责任编辑|审\s*稿)"
    r"\s*[：:]\s*(?P<names>[\u4e00-\u9fff、，, 　 ]{2,120})"
)

AUTHOR_PATTERN = re.compile(r"（(?P<period>清|明|民国|宋|元)）(?P<name>[\u4e00-\u9fff]{2,4})(?P<role>纂修|修订|主编|编|著)")


def stable_entity_id(prefix: str, parts: Iterable[Any]) -> str:
    identity = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:14]
    return f"{prefix}_{digest}"


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip("，。、；：: ")


def context_snippet(text: str, start: int, end: int, radius: int = SNIPPET_RADIUS) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    snippet = text[left:right]
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet


def infer_doc_place(doc: dict[str, Any]) -> str:
    filename = doc.get("source_file_name", "")
    matches = re.findall(r"([\u4e00-\u9fff]{2,8}(?:省|市|府|州|县|区|镇|乡))志", filename)
    if matches:
        return matches[0]
    for marker in ["县志", "区志", "镇志", "府志", "州志", "市志"]:
        idx = filename.find(marker)
        if idx > 0:
            candidate = re.sub(r"^[^\u4e00-\u9fff]+", "", filename[: idx + len(marker) - 1])
            candidate = re.sub(r"^(?:光绪|道光|嘉庆|乾隆|同治|民国|康熙|嘉靖|弘治|宣统|安徽省|江苏省|上海市)\s*", "", candidate)
            if 2 <= len(candidate) <= 8:
                return candidate
    return ""


def build_place_terms(docs: list[dict[str, Any]]) -> tuple[list[str], dict[str, str]]:
    terms = set(PLACE_EXTRA)
    province_by_place: dict[str, str] = {}
    for province, names in REGION_KEYWORDS.items():
        for name in names:
            if len(name) >= 2:
                terms.add(name)
                province_by_place[name] = province
                if not name.endswith(("省", "市", "县", "区", "镇", "府", "州")) and len(name) >= 2:
                    for suffix in ["县", "市", "区", "镇", "府", "州"]:
                        terms.add(name + suffix)
                        province_by_place[name + suffix] = province
    for doc in docs:
        doc_place = infer_doc_place(doc)
        if doc_place:
            terms.add(doc_place)
            region = doc.get("region_guess")
            if region in {"江苏", "安徽", "上海"}:
                province_by_place[doc_place] = region
    return sorted(terms, key=len, reverse=True), province_by_place


def province_for_place(place: str, doc: dict[str, Any], province_by_place: dict[str, str]) -> str:
    if place in province_by_place:
        return province_by_place[place]
    for key, province in province_by_place.items():
        if key in place or place in key:
            return province
    region = doc.get("region_guess")
    return region if region in {"江苏", "安徽", "上海"} else ""


def county_or_city_for_place(place: str, doc: dict[str, Any]) -> str:
    if place.endswith(("县", "市", "区", "镇", "府", "州")):
        return place
    doc_place = infer_doc_place(doc)
    if doc_place:
        return doc_place
    return ""


def nearby_places(text: str, place_terms: list[str], limit: int = 5) -> list[str]:
    hits = []
    for term in place_terms:
        if term in text and term not in hits:
            hits.append(term)
        if len(hits) >= limit:
            break
    return hits


def nearby_period(text: str) -> str:
    matches = PERIOD_PATTERN.findall(text)
    return matches[0] if matches else ""


def iter_term_matches(text: str, terms: list[str]):
    for term in terms:
        if len(term) < 2:
            continue
        for match in re.finditer(re.escape(term), text):
            yield term, match.start(), match.end()


def should_skip_text(row: dict[str, Any]) -> bool:
    text = row.get("text_clean") or ""
    return not text or row.get("needs_ocr") and len(text) < 20


def split_person_names(value: str) -> list[str]:
    value = re.sub(r"[^\u4e00-\u9fff、，, 　 ]", " ", value)
    raw_parts = re.split(r"[、，,]+", value)
    names: list[str] = []
    stopwords = {"主任", "委员", "顾问", "副主任", "成员", "办公室", "地方志", "人民政府", "责任编辑", "审稿"}
    for part in raw_parts:
        part = part.strip()
        if not part:
            continue
        # Handles OCR/layout output like "王宜斌 莫 欣 诸伟奇".
        tokens = [token for token in re.split(r"\s+", part) if token]
        if len(tokens) > 1:
            buffer = ""
            for token in tokens:
                buffer += token
                if 2 <= len(buffer) <= 4:
                    if buffer not in stopwords:
                        names.append(buffer)
                    buffer = ""
            if 2 <= len(buffer) <= 4 and buffer not in stopwords:
                names.append(buffer)
        else:
            compact = normalize_name(part)
            if 2 <= len(compact) <= 4 and compact not in stopwords:
                names.append(compact)
    return list(dict.fromkeys(names))


def role_from_label(label: str) -> str:
    label = normalize_name(label)
    return {
        "顾问": "顾问",
        "主修": "主修",
        "副主编": "副主编",
        "主编": "主编",
        "编纂": "编纂",
        "纂修": "纂修",
        "修订": "修订",
        "作者": "作者",
        "主任": "主任",
        "副主任": "副主任",
        "委员": "委员",
        "责任编辑": "责任编辑",
        "审稿": "审稿",
    }.get(label, label)


def extract_places(rows: list[dict[str, Any]], docs: list[dict[str, Any]], doc_lookup: dict[str, dict[str, Any]], place_terms: list[str], province_by_place: dict[str, str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        if should_skip_text(row):
            continue
        text = row.get("text_clean", "")
        doc = doc_lookup[row["doc_id"]]
        for place, start, end in iter_term_matches(text, place_terms):
            key = (row["doc_id"], place)
            if counts[key] >= MAX_OCCURRENCES_PER_DOC_TERM:
                continue
            snippet = context_snippet(text, start, end)
            counts[key] += 1
            entries.append(
                {
                    "entity_id": stable_entity_id("place", [place, row["doc_id"], row.get("page_number"), counts[key], snippet]),
                    "place_name": place,
                    "normalized_name": normalize_name(place),
                    "province": province_for_place(place, doc, province_by_place),
                    "county_or_city": county_or_city_for_place(place, doc),
                    "doc_id": row["doc_id"],
                    "page_number": row.get("page_number"),
                    "context_snippet": snippet,
                    "confidence": "high" if place in province_by_place or place == infer_doc_place(doc) else "medium",
                }
            )
    return entries


def extract_people(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        if should_skip_text(row):
            continue
        text = row.get("text_clean", "")
        for line_match in PERSON_LINE_PATTERN.finditer(text):
            label = role_from_label(line_match.group("label"))
            segment = line_match.group("names")
            for name in split_person_names(segment):
                key = (row["doc_id"], name)
                if counts[key] >= MAX_OCCURRENCES_PER_DOC_TERM:
                    continue
                counts[key] += 1
                snippet = context_snippet(text, line_match.start(), line_match.end())
                entries.append(
                    {
                        "entity_id": stable_entity_id("person", [name, label, row["doc_id"], row.get("page_number"), counts[key]]),
                        "person_name": name,
                        "role_or_category": label,
                        "dynasty_or_period": nearby_period(snippet),
                        "doc_id": row["doc_id"],
                        "page_number": row.get("page_number"),
                        "context_snippet": snippet,
                        "confidence": "high",
                    }
                )
        for author_match in AUTHOR_PATTERN.finditer(text):
            name = author_match.group("name")
            role = author_match.group("role")
            key = (row["doc_id"], name)
            if counts[key] >= MAX_OCCURRENCES_PER_DOC_TERM:
                continue
            counts[key] += 1
            snippet = context_snippet(text, author_match.start(), author_match.end())
            entries.append(
                {
                    "entity_id": stable_entity_id("person", [name, role, row["doc_id"], row.get("page_number"), counts[key]]),
                    "person_name": name,
                    "role_or_category": role,
                    "dynasty_or_period": author_match.group("period"),
                    "doc_id": row["doc_id"],
                    "page_number": row.get("page_number"),
                    "context_snippet": snippet,
                    "confidence": "high",
                }
            )
    return entries


def extract_transport(rows: list[dict[str, Any]], place_terms: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    counts: Counter[tuple[str, str]] = Counter()
    terms = sorted(TRANSPORT_CATEGORIES, key=len, reverse=True)
    for row in rows:
        if should_skip_text(row):
            continue
        text = row.get("text_clean", "")
        for term, start, end in iter_term_matches(text, terms):
            key = (row["doc_id"], term)
            if counts[key] >= MAX_OCCURRENCES_PER_DOC_TERM:
                continue
            counts[key] += 1
            snippet = context_snippet(text, start, end)
            entries.append(
                {
                    "entity_id": stable_entity_id("transport", [term, row["doc_id"], row.get("page_number"), counts[key]]),
                    "transport_term": term,
                    "category": TRANSPORT_CATEGORIES[term],
                    "related_places": ";".join(nearby_places(snippet, place_terms)),
                    "doc_id": row["doc_id"],
                    "page_number": row.get("page_number"),
                    "context_snippet": snippet,
                    "confidence": "high",
                }
            )
    return entries


def extract_dialect(rows: list[dict[str, Any]], doc_lookup: dict[str, dict[str, Any]], place_terms: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        if should_skip_text(row):
            continue
        text = row.get("text_clean", "")
        for term, start, end in iter_term_matches(text, DIALECT_TERMS):
            key = (row["doc_id"], term)
            if counts[key] >= MAX_OCCURRENCES_PER_DOC_TERM:
                continue
            counts[key] += 1
            snippet = context_snippet(text, start, end)
            places = nearby_places(snippet, place_terms)
            if not places:
                inferred = infer_doc_place(doc_lookup[row["doc_id"]])
                places = [inferred] if inferred else []
            entries.append(
                {
                    "entity_id": stable_entity_id("dialect", [term, row["doc_id"], row.get("page_number"), counts[key]]),
                    "dialect_term": term,
                    "explanation_or_context": snippet,
                    "place": ";".join(places),
                    "doc_id": row["doc_id"],
                    "page_number": row.get("page_number"),
                    "context_snippet": snippet,
                    "confidence": "high" if term in {"方言", "吴语", "江淮官话"} else "medium",
                }
            )
    return entries


def extract_customs(rows: list[dict[str, Any]], doc_lookup: dict[str, dict[str, Any]], place_terms: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    counts: Counter[tuple[str, str]] = Counter()
    terms = sorted(CUSTOM_CATEGORIES, key=len, reverse=True)
    for row in rows:
        if should_skip_text(row):
            continue
        text = row.get("text_clean", "")
        for term, start, end in iter_term_matches(text, terms):
            key = (row["doc_id"], term)
            if counts[key] >= MAX_OCCURRENCES_PER_DOC_TERM:
                continue
            counts[key] += 1
            snippet = context_snippet(text, start, end)
            places = nearby_places(snippet, place_terms)
            if not places:
                inferred = infer_doc_place(doc_lookup[row["doc_id"]])
                places = [inferred] if inferred else []
            entries.append(
                {
                    "entity_id": stable_entity_id("custom", [term, row["doc_id"], row.get("page_number"), counts[key]]),
                    "custom_term": term,
                    "category": CUSTOM_CATEGORIES[term],
                    "place": ";".join(places),
                    "date_or_period": nearby_period(snippet),
                    "doc_id": row["doc_id"],
                    "page_number": row.get("page_number"),
                    "context_snippet": snippet,
                    "confidence": "high",
                }
            )
    return entries


def plausible_relic_name(name: str) -> bool:
    if len(name) < 2 or len(name) > 10:
        return False
    if re.search(r"[第卷章节编目类条款]", name):
        return False
    if re.search(r"(?:文物胜迹|名胜古迹|古迹遗址)$", name):
        return False
    if name in {"文物", "古迹", "遗址", "胜迹", "书院", "文化遗产"}:
        return True
    return True


def relic_name_candidates(text: str):
    trigger_specific = re.compile(
        r"(?:建|创建|重建|修建|捐建|重修|修葺|建为|俗称|名曰|称为|今存|尚存|遗址为|遗址建为)"
        r"(?P<name>[\u4e00-\u9fff]{2,10}(?:遗址|书院|寺|塔|祠|庙|墓|碑|胜迹|文化遗产))"
    )
    titled_specific = re.compile(r"《(?P<name>[\u4e00-\u9fff]{2,10}(?:寺|塔|祠|庙|墓|碑|书院|胜迹))》")
    for pattern in [trigger_specific, titled_specific]:
        for match in pattern.finditer(text):
            name = normalize_name(match.group("name"))
            start, end = match.span("name")
            if plausible_relic_name(name):
                yield name, start, end, "named_relic"
    direct_site = re.compile(r"(?P<name>[\u4e00-\u9fff]{2,8}遗址)")
    for match in direct_site.finditer(text):
        name = normalize_name(match.group("name"))
        if plausible_relic_name(name):
            yield name, match.start("name"), match.end("name"), "named_relic"
    # Generic one-character relic suffixes are too noisy for page-level indexing.
    generic_terms = [term for term in RELIC_TYPES if len(term) >= 2]
    for term in sorted(generic_terms, key=len, reverse=True):
        for match in re.finditer(re.escape(term), text):
            yield term, match.start(), match.end(), "term"


def relic_type_for(name: str) -> str:
    for suffix, relic_type in sorted(RELIC_TYPES.items(), key=lambda item: len(item[0]), reverse=True):
        if name.endswith(suffix) or name == suffix:
            return relic_type
    return "relic"


def extract_relics(rows: list[dict[str, Any]], doc_lookup: dict[str, dict[str, Any]], place_terms: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        if should_skip_text(row):
            continue
        text = row.get("text_clean", "")
        for name, start, end, source_kind in relic_name_candidates(text):
            name = normalize_name(name)
            if len(name) < 2:
                continue
            key = (row["doc_id"], name)
            if counts[key] >= MAX_OCCURRENCES_PER_DOC_TERM:
                continue
            counts[key] += 1
            snippet = context_snippet(text, start, end)
            places = nearby_places(snippet, place_terms)
            if not places:
                inferred = infer_doc_place(doc_lookup[row["doc_id"]])
                places = [inferred] if inferred else []
            entries.append(
                {
                    "entity_id": stable_entity_id("relic", [name, row["doc_id"], row.get("page_number"), counts[key]]),
                    "relic_name": name,
                    "relic_type": relic_type_for(name),
                    "place": ";".join(places),
                    "date_or_period": nearby_period(snippet),
                    "doc_id": row["doc_id"],
                    "page_number": row.get("page_number"),
                    "context_snippet": snippet,
                    "confidence": "high" if source_kind == "named_relic" else "medium",
                }
            )
    return entries


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def write_pair(base_name: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
    write_csv(INDEXES_DIR / f"{base_name}.csv", rows, columns)
    write_jsonl(INDEXES_DIR / f"{base_name}.jsonl", rows)


def main() -> None:
    docs = read_jsonl(METADATA_DIR / "pilot_documents.jsonl")
    rows = read_jsonl(TEXT_CLEAN_DIR / "pilot_pages_clean.jsonl")
    if not docs or not rows:
        raise FileNotFoundError("Missing pilot metadata or clean text. Run earlier pipeline scripts first.")

    doc_lookup = {doc["doc_id"]: doc for doc in docs}
    place_terms, province_by_place = build_place_terms(docs)

    place_rows = extract_places(rows, docs, doc_lookup, place_terms, province_by_place)
    person_rows = extract_people(rows)
    transport_rows = extract_transport(rows, place_terms)
    dialect_rows = extract_dialect(rows, doc_lookup, place_terms)
    custom_rows = extract_customs(rows, doc_lookup, place_terms)
    relic_rows = extract_relics(rows, doc_lookup, place_terms)

    write_pair(
        "place_index",
        place_rows,
        ["entity_id", "place_name", "normalized_name", "province", "county_or_city", "doc_id", "page_number", "context_snippet", "confidence"],
    )
    write_pair(
        "person_index",
        person_rows,
        ["entity_id", "person_name", "role_or_category", "dynasty_or_period", "doc_id", "page_number", "context_snippet", "confidence"],
    )
    write_pair(
        "transport_index",
        transport_rows,
        ["entity_id", "transport_term", "category", "related_places", "doc_id", "page_number", "context_snippet", "confidence"],
    )
    write_pair(
        "dialect_index",
        dialect_rows,
        ["entity_id", "dialect_term", "explanation_or_context", "place", "doc_id", "page_number", "context_snippet", "confidence"],
    )
    write_pair(
        "custom_index",
        custom_rows,
        ["entity_id", "custom_term", "category", "place", "date_or_period", "doc_id", "page_number", "context_snippet", "confidence"],
    )
    write_pair(
        "relic_index",
        relic_rows,
        ["entity_id", "relic_name", "relic_type", "place", "date_or_period", "doc_id", "page_number", "context_snippet", "confidence"],
    )

    summary = {
        "place_index": len(place_rows),
        "person_index": len(person_rows),
        "transport_index": len(transport_rows),
        "dialect_index": len(dialect_rows),
        "custom_index": len(custom_rows),
        "relic_index": len(relic_rows),
        "policy": "Conservative dictionary and explicit-pattern extraction from pilot clean text. Entries are capped per document-term and always include page + context snippet.",
    }
    write_json(INDEXES_DIR / "thematic_index_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

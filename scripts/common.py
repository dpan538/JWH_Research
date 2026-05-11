from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT.parent.parent

SOURCE_MANIFEST_JSON = Path("<TMP>/jiangsu_shanghai_anhui_scan_manifest.json")
SOURCE_MANIFEST_CSV = Path("<TMP>/jiangsu_shanghai_anhui_scan_manifest.csv")

DATA_DIR = PROJECT_ROOT / "data"
MANIFEST_DIR = DATA_DIR / "manifest"
METADATA_DIR = DATA_DIR / "metadata"
TEXT_RAW_DIR = DATA_DIR / "text_raw"
OCR_RAW_DIR = DATA_DIR / "ocr_raw"
TEXT_CLEAN_DIR = DATA_DIR / "text_clean"
TEXT_ANNOTATED_DIR = DATA_DIR / "text_annotated"
INDEXES_DIR = DATA_DIR / "indexes"
QC_DIR = DATA_DIR / "quality_control"
READING_EXPORTS_DIR = DATA_DIR / "reading_exports"

ALL_DATA_DIRS = [
    MANIFEST_DIR,
    METADATA_DIR,
    TEXT_RAW_DIR,
    OCR_RAW_DIR,
    TEXT_CLEAN_DIR,
    TEXT_ANNOTATED_DIR,
    INDEXES_DIR,
    QC_DIR,
    READING_EXPORTS_DIR,
]

TEXT_THRESHOLD = 20

REGION_KEYWORDS = {
    "江苏": [
        "江苏", "苏州", "吴县", "吴江", "常熟", "太仓", "昆山", "金阊", "虎邱", "寒山寺",
        "无锡", "江阴", "宜兴", "常州", "镇江", "丹徒", "句容", "扬州", "泰州", "南通",
        "盐城", "淮安", "徐州", "连云港", "南京", "金陵", "江宁", "建康", "六合", "高淳",
    ],
    "安徽": [
        "安徽", "皖", "徽州", "黄山", "歙县", "黟县", "休宁", "祁门", "绩溪", "旌德",
        "安庆", "桐城", "怀宁", "枞阳", "太湖", "宿松", "池州", "贵池", "芜湖", "铜陵",
        "马鞍山", "宁国", "滁州", "天长", "来安", "凤阳", "寿州", "六安", "庐州", "庐江",
        "巢湖", "蚌埠", "宿州", "亳州", "阜阳", "颍州", "临泉", "太和", "界首",
    ],
    "上海": [
        "上海", "松江", "华亭", "青浦", "川沙", "奉贤", "南汇", "静安", "嘉定", "金山",
        "罗店", "大场", "江湾", "枫泾", "朱泾", "月浦", "杨行", "洋泾", "南翔", "安亭",
    ],
}

SEMANTIC_TAG_PATTERNS = {
    "places": REGION_KEYWORDS["江苏"] + REGION_KEYWORDS["安徽"] + REGION_KEYWORDS["上海"] + [
        "府", "州", "县", "镇", "乡", "里", "村", "城", "山", "湖", "河", "港", "桥",
    ],
    "people": [
        "人物", "列传", "名宦", "乡贤", "进士", "举人", "贡生", "孝子", "烈女", "节妇",
        "传", "墓志", "姓氏", "氏族",
    ],
    "dates": [
        "宋", "元", "明", "清", "民国", "弘治", "嘉靖", "万历", "崇祯", "康熙", "雍正",
        "乾隆", "嘉庆", "道光", "咸丰", "同治", "光绪", "宣统", "共和国",
    ],
    "transport": [
        "交通", "道路", "公路", "铁路", "航运", "民航", "驿", "驿站", "运河", "港", "码头",
        "桥", "车", "船", "渡", "邮电",
    ],
    "dialect": ["方言", "音系", "声母", "韵母", "声调", "土语", "俗语", "吴语", "江淮官话"],
    "customs": ["风俗", "民俗", "岁时", "节令", "婚丧", "祭祀", "庙会", "风土", "习俗"],
    "relics": ["文物", "古迹", "遗址", "碑", "墓", "寺", "塔", "祠", "庙", "书院", "胜迹"],
    "institutions": ["机构", "县署", "衙署", "政府", "委员会", "学校", "会社", "公所", "局", "所"],
    "taxation": ["赋", "税", "税务", "田赋", "漕", "盐课", "厘金", "财政", "钱粮"],
    "education": ["教育", "学校", "书院", "学堂", "小学", "中学", "师范", "科举", "儒学"],
    "industry": ["工业", "农业", "商业", "手工业", "纺织", "陶瓷", "冶金", "盐业", "粮食", "工厂"],
}


def ensure_dirs() -> None:
    for directory in ALL_DATA_DIRS:
        directory.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def copy_source_manifests() -> None:
    ensure_dirs()
    if SOURCE_MANIFEST_JSON.exists():
        shutil.copy2(SOURCE_MANIFEST_JSON, MANIFEST_DIR / "source_manifest.json")
    if SOURCE_MANIFEST_CSV.exists():
        shutil.copy2(SOURCE_MANIFEST_CSV, MANIFEST_DIR / "source_manifest.csv")


def normalize_for_id(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def stable_doc_id(record: dict[str, Any]) -> str:
    identity = "|".join(
        [
            normalize_for_id(record.get("file_name", "")),
            str(record.get("size_bytes", "")),
            str(record.get("page_count", "")),
        ]
    )
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
    return f"swhgz_{digest}"


def clean_whitespace(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def safe_filename(value: str, limit: int = 96) -> str:
    value = re.sub(r"[\\/:\*\?\"<>\|\n\r\t]+", "_", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > limit:
        value = value[:limit].rstrip()
    return value or "untitled"


def resolve_source_path(record: dict[str, Any]) -> Path:
    path_text = record.get("source_path_current") or record.get("path") or ""
    path = Path(path_text)
    if path.exists():
        return path
    fallback = SOURCE_ROOT / record.get("source_file_name", record.get("file_name", ""))
    return fallback


def doc_text_from_binary(path: Path) -> tuple[str, dict[str, Any]]:
    data = path.read_bytes()
    candidates: list[dict[str, Any]] = []
    for enc in ["utf-16le", "gb18030", "big5", "utf-8"]:
        decoded = data.decode(enc, errors="ignore")
        seqs = []
        pattern = r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffefA-Za-z0-9，。、；：！？（）《》“”‘’·—\-\s]{20,}"
        for match in re.findall(pattern, decoded):
            cleaned = clean_whitespace(match)
            cjk = sum("\u4e00" <= c <= "\u9fff" for c in cleaned)
            if len(cleaned) >= 20 and cjk >= 5:
                seqs.append(cleaned)
        sample = "".join(seqs[:200])
        cjk_total = sum("\u4e00" <= c <= "\u9fff" for c in sample)
        common_total = sum(c in "的一是在不了有和人这中大为上个国以要时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反明看原又么利比或但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别手角期根论运农指几九区强放决西被干做必战先回则任取据处队南给色光门即保治北造百规热领七海口东导器压志世金增争济阶油思术极交受联认六共权收证改清美再采转更单风切打白教速花带安场身车例真务具万每目至达走积示议声报斗完类八离华名确才科张信马节话米整空元况今集温传土许步群广石记需段研界拉林律叫且究观越织装影算低持音众书布复容儿须际商非验连断深难近矿千周委素技备半办青省列习响约支般史感劳便团往酸历市克何除消构府称太准精值号率族维划选标写存候毛亲快效斯院查江型眼王按格养易置派层片始却专状育厂京识适属圆包火住调满县志" for c in sample)
        score = cjk_total + 3 * common_total + 20 * sum(("志" in s or "县" in s or "目录" in s or "序" in s) for s in seqs[:20])
        candidates.append(
            {
                "encoding": enc,
                "score": score,
                "seq_count": len(seqs),
                "cjk_chars_sampled": cjk_total,
                "common_ratio": round(common_total / cjk_total, 3) if cjk_total else 0,
                "text": "\n\n".join(seqs),
            }
        )
    best = max(candidates, key=lambda item: item["score"])
    confidence = "medium"
    if best["common_ratio"] >= 0.42 and best["seq_count"] > 20:
        confidence = "high"
    if best["common_ratio"] < 0.2:
        confidence = "low_garbled_or_image_doc"
    diagnostics = {
        "method": "binary_decode_heuristic",
        "best_encoding": best["encoding"],
        "confidence": confidence,
        "seq_count": best["seq_count"],
        "cjk_chars_sampled": best["cjk_chars_sampled"],
        "common_ratio": best["common_ratio"],
    }
    return best["text"], diagnostics


def split_doc_text(text: str, chunk_size: int = 2500) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        if current and current_len + len(paragraph) > chunk_size:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(paragraph)
        current_len += len(paragraph)
    if current:
        chunks.append("\n\n".join(current))
    return chunks or ([text[:chunk_size]] if text else [])


def semantic_tags_for_text(text: str) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for tag, keywords in SEMANTIC_TAG_PATTERNS.items():
        hits = sorted({keyword for keyword in keywords if keyword and keyword in text})
        if tag == "dates":
            year_hits = re.findall(r"(?:公元)?(?:1[0-9]{3}|20[0-9]{2})年?", text)
            reign_hits = re.findall(r"(?:康熙|雍正|乾隆|嘉庆|道光|咸丰|同治|光绪|宣统|民国|弘治|嘉靖|万历|崇祯)[一二三四五六七八九十百元0-9]{0,6}年?", text)
            hits = sorted(set(hits + year_hits[:20] + reign_hits[:20]))
        if hits:
            found[tag] = hits[:50]
    return found


def counter_to_dict(counter: Counter) -> dict[str, int]:
    return {str(key): int(value) for key, value in counter.items()}


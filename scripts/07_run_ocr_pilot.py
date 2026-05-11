from __future__ import annotations

import argparse
import shutil
from datetime import datetime

from common import METADATA_DIR, OCR_RAW_DIR, read_jsonl, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Safe pilot OCR runner. Dry-run by default.")
    parser.add_argument("--execute", action="store_true", help="Actually run OCR. Not recommended until the pilot queue is reviewed.")
    parser.add_argument("--max-pages", type=int, default=25, help="Maximum pages to OCR when --execute is used.")
    args = parser.parse_args()

    queue = read_jsonl(METADATA_DIR / "ocr_queue_pilot.jsonl")
    if not queue:
        raise FileNotFoundError("Run 06_prepare_ocr_queue.py first.")

    tesseract_path = shutil.which("tesseract")
    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": "execute" if args.execute else "dry_run",
        "queued_records": len(queue),
        "max_pages": args.max_pages,
        "tesseract_available": bool(tesseract_path),
        "tesseract_path": tesseract_path,
        "note": "This script is intentionally conservative. It does not run full-corpus OCR.",
    }

    if not args.execute:
        report["status"] = "not_run_dry_run_only"
    elif not tesseract_path:
        report["status"] = "not_run_tesseract_missing"
    else:
        report["status"] = "not_implemented_rendering_step"
        report["message"] = "Next implementation step: render selected PDF pages to images, then call tesseract with Chinese language data."

    write_json(OCR_RAW_DIR / "pilot_ocr_run_report.json", report)
    print(report["status"])


if __name__ == "__main__":
    main()


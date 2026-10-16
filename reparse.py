"""
Parse ulang rawText hasil ktp_ocr.py --out tanpa menjalankan model.

    python reparse.py results/uji-1
"""

import json
import sys
from pathlib import Path

from ktp_ocr import summarize
from ktp_parser import parse_ktp


def main() -> int:
    out_dir = Path(sys.argv[1])
    results = []
    for path in sorted(out_dir.glob("*.json")):
        if path.name == "summary.json":
            continue
        saved = json.loads(path.read_text())
        parsed = parse_ktp(saved["rawText"]).to_dict()
        saved.update(parsed)
        path.write_text(json.dumps(saved, ensure_ascii=False, indent=2))
        results.append(saved)
    summary = summarize(results)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

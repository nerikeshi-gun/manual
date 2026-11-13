"""各社の output/raw/<maker>_manuals.csv を連結して output/manuals.csv を作る。

    python -m collector.combine
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "output" / "raw"
OUT = ROOT / "output" / "manuals.csv"

COLUMNS = [
    "maker", "domain", "product_category", "model_raw", "model_normalized", "title", "url",
    "url_type", "source_method", "first_seen", "http_status", "checked_at",
    "model_unconfirmed", "discontinued",
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    counts: Counter = Counter()
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, COLUMNS)
        writer.writeheader()
        for path in sorted(RAW.glob("*_manuals.csv")):
            with path.open(encoding="utf-8", newline="") as src:
                for row in csv.DictReader(src):
                    writer.writerow({k: row.get(k, "") for k in COLUMNS})
                    counts[row["maker"]] += 1
    for maker, n in counts.items():
        print(f"{maker}\t{n}")
    print(f"total\t{sum(counts.values())}")


if __name__ == "__main__":
    main()

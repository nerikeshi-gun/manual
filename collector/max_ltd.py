"""マックス（住宅設備機器: www.max-ltd.co.jp/support/download/dry-fan/torisetsu/）の取説URL収集。

住設（浴室暖房・換気・乾燥機、換気扇、床暖房、火災警報器、ディスポーザ等）の資料ダウンロードページ1枚に、
カテゴリ見出し（h2）ごとの表（行 th = 製品名, 列 = 取扱説明書／取付説明書／仕様書／自己適合宣言書／CAD）がある。
取扱説明書・取付説明書・設置説明書の列のみ採る（仕様書・自己適合宣言書・CADは取説ではないので対象外）。
建築工具・オフィス機器・農業資材の取説ページは住設ではないので対象外（notes に記載）。

    python -m collector.max_ltd run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.common import LOGS, NOTES, RAW, check_urls, decode, now, squash, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

PAGE = "https://www.max-ltd.co.jp/support/download/dry-fan/torisetsu/"
MAKER, DOMAIN, KEY = "マックス", "住設", "max"
KEEP = ("取扱説明書", "取付説明書", "設置説明書")
SIZE = re.compile(r"\s*\[PDF:[^\]]*\]\s*$")


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    resp = c.get(PAGE)
    soup = BeautifulSoup(decode(resp), "lxml")
    rows, items, skipped = [], [], Counter()
    for table in soup.select("table.table__matrix"):
        sec = table.find_previous("h2")
        category = sec.get_text(" ", strip=True) if sec else ""
        heads = [th.get_text(" ", strip=True) for th in table.select("thead th")]
        for tr in table.select("tbody tr"):
            th = tr.find("th")
            model = th.get_text(" ", strip=True) if th else ""
            for col, td in zip(heads[1:], tr.find_all("td")):
                for a in td.find_all("a", href=True):
                    label = SIZE.sub("", a.get_text(" ", strip=True))
                    url = urljoin(resp.url, a["href"])
                    items.append({"category": category, "model": model, "column": col, "label": label, "url": url})
                    if col not in KEEP:
                        skipped[col] += 1
                        continue
                    rows.append({
                        "maker": MAKER, "domain": DOMAIN, "product_category": category, "model_raw": model,
                        "model_normalized": squash(model), "title": label or col, "url": url,
                        "url_type": "pdf" if url.lower().endswith(".pdf") else "html", "source_method": "crawl",
                        "first_seen": "", "http_status": "", "checked_at": "", "model_unconfirmed": "0" if model else "1",
                        "discontinued": "",
                    })
    stats: Counter = Counter()
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    url_models = defaultdict(set)
    for r in rows:
        url_models[r["url"]].add(r["model_raw"])
    anomalies = [{"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": u}
                 for u, ms in url_models.items() if len(ms) > 1]
    write_jsonl(RAW / f"{KEY}_pages.jsonl", [{"url": PAGE, "status": resp.status_code, "items": items, "fetched_at": now()}])
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"rows": len(rows), "unique_urls": len(url_models), "models": len({r["model_raw"] for r in rows}),
               "http": Counter(r["http_status"] for r in rows), "per_title": Counter(r["title"] for r in rows),
               "skipped_columns": skipped, "per_category": Counter(r["product_category"] for r in rows),
               "shared_url": len(anomalies), **stats}
    (RAW / f"{KEY}_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_subparsers(required=True).add_parser("run").set_defaults(func=run)
    args = p.parse_args()
    NOTES.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()

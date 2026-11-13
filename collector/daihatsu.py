"""ダイハツ（www.daihatsu.co.jp/service/torisetu/）の車両取扱説明書URL収集。

車種一覧 service/torisetu/index.htm（と index2.htm）→ 車種のご利用条件 <車種>/index.htm（「同意する」は
<車種>/index_2.htm へ移るだけ。ユーザーの包括承認あり）→ <車種>/index_2.htm に PDF と説明（p.torisetu_text,
例「車両（詳細版）（2026年7月～）」）が並ぶ。
model_raw は「車種／適用期間」（指示書の車種/年式/グレード）。

    python -m collector.daihatsu run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.common import LOGS, NOTES, RAW, check_urls, decode, name_key, now, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

BASE = "https://www.daihatsu.co.jp/service/torisetu/"
MAKER, DOMAIN, KEY = "ダイハツ", "車載", "daihatsu"


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    slugs = []
    for page in ("index.htm", "index2.htm"):
        resp = c.get(BASE + page)
        if resp.status_code != 200:
            continue
        for a in BeautifulSoup(decode(resp), "lxml").find_all("a", href=True):
            m = re.match(rf"{re.escape(BASE)}([a-z0-9_\-]+)/index\.htm$", urljoin(resp.url, a["href"]))
            if m and m.group(1) not in slugs:
                slugs.append(m.group(1))
    rows, pages = [], []
    for slug in slugs:
        c.get(f"{BASE}{slug}/index.htm")  # ご利用条件ページ
        resp = c.get(f"{BASE}{slug}/index_2.htm")
        soup = BeautifulSoup(decode(resp), "lxml")
        name_p = soup.select_one("p.cach_text3")
        car = name_p.get_text(" ", strip=True) if name_p else slug
        got = 0
        for a in soup.find_all("a", href=True):
            url = urljoin(resp.url, a["href"])
            if not url.lower().endswith(".pdf"):
                continue
            box = a.find_parent("div")
            label_p = box.select_one("p.torisetu_text") if box else None
            label = re.sub(r"\s+", "", label_p.get_text("", strip=True)) if label_p else ""
            period = (re.search(r"[（(](\d{4}年\d{1,2}月[^（）()]*)[)）]\s*$", label) or [None, ""])[1]
            doc = re.sub(r"[（(]\d{4}年\d{1,2}月[^（）()]*[)）]\s*$", "", label) or "取扱説明書"
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": "自動車",
                "model_raw": "／".join(x for x in (car, period) if x), "model_normalized": name_key(car), "title": doc,
                "url": url, "url_type": "pdf", "source_method": "crawl", "first_seen": "", "http_status": "",
                "checked_at": "", "model_unconfirmed": "0", "discontinued": "",
            })
            got += 1
        pages.append({"slug": slug, "car": car, "status": resp.status_code, "links": got, "fetched_at": now()})
        print(f"  {slug} {car}: {got}", flush=True)
    rows = list({(r["url"], r["model_raw"], r["title"]): r for r in rows}.values())
    stats: Counter = Counter()
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    url_models = defaultdict(set)
    for r in rows:
        url_models[r["url"]].add(r["model_raw"])
    anomalies = [{"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": u}
                 for u, ms in url_models.items() if len(ms) > 1]
    anomalies += [{"type": "no_links", "model": p["car"], "detail": p["status"], "url": f"{BASE}{p['slug']}/index_2.htm"} for p in pages if not p["links"]]
    write_jsonl(RAW / f"{KEY}_pages.jsonl", pages)
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"cars": len(pages), "rows": len(rows), "unique_urls": len(url_models), "http": Counter(r["http_status"] for r in rows),
               "per_doc": Counter(r["title"] for r in rows).most_common(10), "anomalies": Counter(a["type"] for a in anomalies), **stats}
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

"""パナソニック（ストラーダ／カー用品: panasonic.jp/car/customer/manual/）の取説URL収集。

旧URL car.panasonic.jp/support/manual/navi/agree.html は panasonic.jp の同意ページへ移転。
同意ページの「同意する」はカテゴリ一覧（index.html）へのリンク。規約同意はユーザー承認済み（2026-11-13）。
各カテゴリ一覧は 年 → dl（dt=品番, dd=PDFリンク）の構造。PDFは car.panasonic.jp 上。

    python -m collector.strada run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from collector.common import LOGS, NOTES, RAW, check_urls, decode, now, squash, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

BASE = "https://panasonic.jp/car/customer/manual/"
MAKER, DOMAIN, KEY = "パナソニック（ストラーダ）", "車載", "strada"
MODEL_TEXT = re.compile(r"[A-Z]{2,4}-[A-Z0-9]{3,}[A-Z0-9\-]*")
SIZE = re.compile(r"\s*\(\s*[\d.,]+\s*[KMG]?B\s*\)\s*$", re.I)


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    c.get(BASE + "navi/agree.html")  # ご利用の条件（同意は index.html へのリンク）
    first = BeautifulSoup(decode(c.get(BASE + "navi/index.html")), "lxml")
    cats = {}
    for a in first.find_all("a", href=True):
        u = urljoin(BASE + "navi/index.html", a["href"]).split("#")[0]
        if re.match(rf"{re.escape(BASE)}[a-z0-9_\-]+/index\.html$", u):
            cats.setdefault(u, a.get_text(" ", strip=True))
    pages, rows, anomalies = [], [], []
    for url, label in cats.items():
        resp = c.get(url)
        soup = BeautifulSoup(decode(resp), "lxml")
        entries = []
        for dl in soup.find_all("dl"):
            block = dl.find_parent("div", class_="mb20")
            year = ""
            if block:
                h = block.find(["h2", "h3", "h4", "p"], string=re.compile(r"\d{4}年"))
                year = h.get_text(strip=True) if h else (re.search(r"(\d{4})年", block.get_text(" ", strip=True)[:20]) or [""])[0]
            for dt in dl.find_all("dt"):
                dd = dt.find_next_sibling("dd")
                if not dd:
                    continue
                model = dt.get_text(" ", strip=True)
                for a in dd.find_all("a", href=True):
                    href = urljoin(resp.url, a["href"])
                    if not urlsplit(href).path.lower().endswith(".pdf"):
                        continue
                    title = SIZE.sub("", a.get_text(" ", strip=True))
                    entries.append({"model": model, "year": year, "href": href, "label": title})
                    rows.append({
                        "maker": MAKER, "domain": DOMAIN, "product_category": label, "model_raw": model,
                        "model_normalized": squash(model), "title": title, "url": href, "url_type": "pdf",
                        "source_method": "crawl", "first_seen": "", "http_status": "", "checked_at": "",
                        "model_unconfirmed": "0", "discontinued": "",
                    })
        if not entries:
            # dl 構造でないページ（SSD/HDD/カメラ等）：章立ての取説ページ（.../data/*.html）や PDF へのリンクを、
            # 直前に現れる品番（CN-xxxx 等）に結びつける
            for a in soup.find_all("a", href=True):
                href = urljoin(resp.url, a["href"])
                path = urlsplit(href).path.lower()
                if "/support/manual/" not in path or not (path.endswith(".pdf") or "/data" in path):
                    continue
                prev = a.find_previous(string=MODEL_TEXT)
                model = MODEL_TEXT.search(prev).group(0) if prev else ""
                title = SIZE.sub("", a.get_text(" ", strip=True))
                entries.append({"model": model, "year": "", "href": href, "label": title})
                rows.append({
                    "maker": MAKER, "domain": DOMAIN, "product_category": label, "model_raw": model,
                    "model_normalized": squash(model), "title": title, "url": href,
                    "url_type": "pdf" if path.endswith(".pdf") else "html", "source_method": "crawl",
                    "first_seen": "", "http_status": "", "checked_at": "",
                    "model_unconfirmed": "0" if model else "1", "discontinued": "",
                })
        if "末尾にＡを付け" in soup.get_text():
            anomalies.append({"type": "model_suffix_note", "model": "", "detail": "説明書に記載の品番は、末尾にＡを付け置き換えて読む", "url": url})
        pages.append({"url": url, "category": label, "status": resp.status_code, "entries": entries, "fetched_at": now()})
        print(f"  {label}: {len(entries)}", flush=True)
    stats: Counter = Counter()
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    url_models = defaultdict(set)
    for r in rows:
        url_models[r["url"]].add(r["model_raw"])
    anomalies += [{"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": u}
                  for u, ms in url_models.items() if len(ms) > 1]
    write_jsonl(RAW / f"{KEY}_pages.jsonl", pages)
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"category_pages": len(pages), "rows": len(rows), "unique_urls": len(url_models),
               "models": len({r["model_raw"] for r in rows}), "http": Counter(r["http_status"] for r in rows),
               "per_category": {p["category"]: len(p["entries"]) for p in pages}, **stats}
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

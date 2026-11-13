"""バルミューダ（www.balmuda.com/jp/support/）の取説URL収集。

製品サポートページは十数件のみ。サポートトップの製品一覧（section-model）から各ページを開き、PDFリンクを拾う。

    python -m collector.balmuda run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from collector.common import LOGS, NOTES, RAW, check_urls, decode, now, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

BASE = "https://www.balmuda.com/jp/support/"
MAKER, DOMAIN, KEY = "バルミューダ", "家電", "balmuda"
MODEL = re.compile(r"(?<![A-Z0-9])([A-Z]{1,4}-?\d{2,}[A-Z0-9]*(?:-[A-Z0-9]{1,3})?)(?![A-Z0-9])")


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    top = BeautifulSoup(decode(c.get(BASE)), "lxml")
    targets = []
    for sec in top.select("[class*=section-model]"):
        cat = next((x[2:] for x in sec.get("class", []) if x.startswith("--")), "")
        for a in sec.select("a.lyt-list__link[href]"):
            targets.append({"url": urljoin(BASE, a["href"]), "category": cat, "label": a.get_text(" ", strip=True)})
    eol = decode(c.get(BASE + "end-of-life/"))
    eol_models = set(MODEL.findall(unicodedata.normalize("NFKC", eol).upper()))
    pages, rows, anomalies = [], [], []
    for t in targets:
        resp = c.get(t["url"])
        soup = BeautifulSoup(decode(resp), "lxml")
        links = [{"href": urljoin(resp.url, a["href"]), "label": a.get_text(" ", strip=True)}
                 for a in soup.find_all("a", href=True) if urlsplit(urljoin(resp.url, a["href"])).path.lower().endswith(".pdf")]
        models = MODEL.findall(unicodedata.normalize("NFKC", t["label"]).upper())
        pages.append({**t, "status": resp.status_code, "links": links, "models": models, "fetched_at": now()})
        if not links:
            anomalies.append({"type": "no_manual_links", "model": " ".join(models), "detail": t["label"], "url": t["url"]})
            continue
        if len(models) > 1:
            anomalies.append({"type": "multi_model_page", "model": " ".join(models), "detail": t["label"], "url": t["url"]})
        for link in links:
            in_name = [m for m in models if m in urlsplit(link["href"]).path.upper()]
            for model in in_name or models or [""]:
                rows.append({
                    "maker": MAKER, "domain": DOMAIN, "product_category": t["category"], "model_raw": model,
                    "model_normalized": model, "title": link["label"], "url": link["href"], "url_type": "pdf",
                    "source_method": "crawl", "first_seen": "", "http_status": "", "checked_at": "",
                    "model_unconfirmed": "0" if model else "1",
                    "discontinued": "1" if model in eol_models else "",
                })
    stats: Counter = Counter()
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    write_jsonl(RAW / f"{KEY}_pages.jsonl", pages)
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"support_pages": len(pages), "pages_with_pdf": sum(bool(p["links"]) for p in pages), "rows": len(rows),
               "http": Counter(r["http_status"] for r in rows), **stats}
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

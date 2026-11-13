"""NEC Aterm（www.aterm.jp/support/manual/）の取説URL収集。

マニュアルトップに並ぶ機種（/support/manual/<機種>/index.html）を現行品として扱い、各ページのPDFを拾う。
旧機種は別の一覧（/support/manual2/support/manual/）にあり、--phase rest で取る。

    python -m collector.aterm run --phase current|rest
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from collector.common import (LOGS, NOTES, RAW, check_urls, decode, load_jsonl, now, squash, write_anomalies,
                              write_jsonl, write_rows)
from collector.polite import PoliteClient

SITE = "https://www.aterm.jp"
MAKER, DOMAIN, KEY = "NEC（Aterm）", "通信", "aterm"
PAGES = RAW / f"{KEY}_pages.jsonl"
DOC_WORDS = ("説明書", "マニュアル", "ガイド", "お使いになる前に", "はじめに", "設定")


def run(args: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    if args.phase == "current":
        index = f"{SITE}/support/manual/"
        pattern = re.compile(r"/support/manual/([a-z0-9\-]+)/index\.html$")
    else:
        index = f"{SITE}/support/manual2/support/manual/index.html"
        pattern = re.compile(r"/support/manual2/support/manual/(\d{6}-\d{3})\.html$")
    top = BeautifulSoup(decode(c.get(index)), "lxml")
    targets = {}
    for a in top.find_all("a", href=True):
        u = urljoin(index, a["href"]).split("#")[0]
        m = pattern.search(u)
        if m:
            targets.setdefault(u, a.get_text(" ", strip=True))
    done = {p["url"] for p in load_jsonl(PAGES)}
    with PAGES.open("a", encoding="utf-8") as out:
        for url, label in targets.items():
            if url in done:
                continue
            resp = c.get(url)
            soup = BeautifulSoup(decode(resp), "lxml")
            title = soup.title.get_text(strip=True).split("｜")[0] if soup.title else label
            links = []
            for a in soup.find_all("a", href=True):
                href = urljoin(resp.url, a["href"]).split("#")[0]
                text = a.get_text(" ", strip=True)
                if urlsplit(href).path.lower().endswith(".pdf") and any(w in text for w in DOC_WORDS + ("PDF",)):
                    links.append({"href": href, "label": text})
            out.write(json.dumps({"url": url, "phase": args.phase, "status": resp.status_code, "model": title or label,
                                  "links": links, "fetched_at": now()}, ensure_ascii=False) + "\n")
            out.flush()
    build(c)


def build(c: PoliteClient) -> None:
    pages = list({p["url"]: p for p in load_jsonl(PAGES)}.values())
    rows, anomalies, stats = [], [], Counter()
    for p in pages:
        if not p["links"]:
            anomalies.append({"type": "no_manual_links", "model": p["model"], "detail": p["status"], "url": p["url"]})
            continue
        model = re.sub(r"^Aterm\s*", "", p["model"]).strip()
        for l in {l["href"]: l for l in p["links"]}.values():
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": "ルーター", "model_raw": model,
                "model_normalized": squash(model), "title": l["label"], "url": l["href"], "url_type": "pdf",
                "source_method": "crawl", "first_seen": "", "http_status": "", "checked_at": "",
                "model_unconfirmed": "0", "discontinued": "0" if p["phase"] == "current" else "",
            })
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    url_models = defaultdict(set)
    for r in rows:
        url_models[r["url"]].add(r["model_raw"])
    anomalies += [{"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": u}
                  for u, ms in url_models.items() if len(ms) > 1]
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"pages": len(pages), "rows": len(rows), "unique_urls": len(url_models),
               "models_with_manual": len({r["model_raw"] for r in rows}), "http": Counter(r["http_status"] for r in rows),
               "anomalies": Counter(a["type"] for a in anomalies), **stats}
    (RAW / f"{KEY}_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    r = p.add_subparsers(required=True).add_parser("run")
    r.add_argument("--phase", choices=["current", "rest"], default="current")
    r.set_defaults(func=run)
    args = p.parse_args()
    NOTES.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()

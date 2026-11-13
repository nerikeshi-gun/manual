"""楽天モバイル（network.mobile.rakuten.co.jp）の端末取説URL収集。

サイトマップの製品ページ（/product/<種別>/<製品>/）を読み、PDFの取説リンクを拾う。

    python -m collector.rakuten run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from collector.common import (LOGS, NOTES, RAW, check_urls, decode, load_jsonl, now, run_parallel, write_anomalies,
                              write_jsonl, write_rows)
from collector.polite import PoliteClient, RobotsDisallowed

SITE = "https://network.mobile.rakuten.co.jp"
MAKER, DOMAIN, KEY = "楽天モバイル", "通信", "rakuten"
PAGES = RAW / f"{KEY}_pages.jsonl"
DOC_WORDS = ("取扱説明書", "説明書", "マニュアル", "ガイド")


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    urls = re.findall(r"<loc>([^<]+)", c.get(f"{SITE}/sitemap.xml").text)
    targets = [u for u in urls if re.match(rf"{re.escape(SITE)}/product/[^/]+/[^/]+/$", u)]
    done = {p["url"] for p in load_jsonl(PAGES)}
    todo = [u for u in targets if u not in done]
    print(f"product pages {len(targets)}, to fetch {len(todo)}", flush=True)
    lock = threading.Lock()

    def one(url):
        try:
            resp = c.get(url)
        except (RobotsDisallowed, requests.RequestException) as exc:
            print(f"error {url}: {type(exc).__name__}", flush=True)
            return None
        if resp.status_code in (403, 429) or resp.status_code >= 500:
            time.sleep(60)
            return "blocked"
        soup = BeautifulSoup(decode(resp), "lxml")
        links = []
        for a in soup.find_all("a", href=True):
            href = urljoin(resp.url, a["href"].strip())
            label = a.get_text(" ", strip=True)
            if urlsplit(href).path.lower().endswith(".pdf") and any(w in label for w in DOC_WORDS):
                links.append({"href": href, "label": label})
        title = soup.title.get_text(strip=True).split("|")[0].strip() if soup.title else ""
        text = soup.get_text(" ", strip=True)
        rec = {"url": url, "status": resp.status_code, "title": title, "links": links,
               "sale_ended": any(k in text for k in ("販売終了", "販売を終了")), "fetched_at": now()}
        with lock, PAGES.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return None

    run_parallel(todo, one, progress_every=100)

    rows, anomalies, stats = [], [], Counter()
    pages = list({p["url"]: p for p in load_jsonl(PAGES)}.values())
    for p in pages:
        kind = urlsplit(p["url"]).path.split("/")[2]
        for l in {l["href"]: l for l in p["links"]}.values():
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": kind, "model_raw": p["title"],
                "model_normalized": re.sub(r"\s+", " ", p["title"]).upper(),
                "title": re.sub(r"を見る$", "", l["label"]).strip(), "url": l["href"], "url_type": "pdf",
                "source_method": "sitemap", "first_seen": "", "http_status": "", "checked_at": "",
                "model_unconfirmed": "0", "discontinued": "1" if p.get("sale_ended") else "0",
            })
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    url_models = defaultdict(set)
    for r in rows:
        url_models[r["url"]].add(r["model_raw"])
    anomalies += [{"type": "shared_url", "model": " / ".join(sorted(ms)[:10]), "detail": len(ms), "url": u}
                  for u, ms in url_models.items() if len(ms) > 1]
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"product_pages": len(pages), "pages_with_manual": sum(bool(p["links"]) for p in pages), "rows": len(rows),
               "unique_urls": len(url_models), "http": Counter(r["http_status"] for r in rows), **stats,
               "kinds": Counter(r["product_category"] for r in rows)}
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

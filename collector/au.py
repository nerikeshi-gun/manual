"""au（www.au.com/support/service/mobile/manual/）の取説URL収集。

サイトマップには一覧ページしか載っていないため、取説コーナー配下（種別 → メーカー）だけを巡回する。
メーカー一覧ページに各機種のPDFが直接並んでおり、PDFのパス（/guide/manual/<機種>/pdf/）から機種を特定する。

    python -m collector.au crawl      # 取説コーナーを巡回してPDFを集める
    python -m collector.au catalog    # 製品ページ（/mobile/product/）を巡回し現行機種を特定
    python -m collector.au build
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict, deque
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from collector.common import (LOGS, NOTES, RAW, check_urls, decode, load_jsonl, now, scan_catalog, squash,
                              write_anomalies, write_jsonl, write_rows)
from collector.polite import PoliteClient, RobotsDisallowed

SITE = "https://www.au.com"
ROOT_PATH = "/support/service/mobile/manual/"
MAKER, DOMAIN, KEY = "au", "通信", "au"
PAGES, CURRENT = RAW / f"{KEY}_pages.jsonl", RAW / f"{KEY}_current.json"
ROWS, ANOMALIES = RAW / f"{KEY}_manuals.csv", RAW / f"{KEY}_anomalies.csv"
MODEL_DIR = re.compile(r"/manual/([a-z0-9][a-z0-9\-_]*)/pdf/", re.I)
TORISETSU_DIR = re.compile(r"/publish/torisetsu/pdf/([a-z0-9\-_]+?)(?:_|\.pdf)", re.I)
_client: PoliteClient | None = None


def client() -> PoliteClient:
    global _client
    if _client is None:
        _client = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    return _client


def clean(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def crawl(_: argparse.Namespace) -> None:
    c = client()
    start = SITE + ROOT_PATH
    queue, seen, pages = deque([start]), {start}, []
    while queue:
        url = queue.popleft()
        try:
            resp = c.get(url)
        except (RobotsDisallowed, requests.RequestException):
            continue
        if resp.status_code != 200:
            pages.append({"url": url, "status": resp.status_code, "links": []})
            continue
        soup = BeautifulSoup(decode(resp), "lxml")
        crumb = soup.title.get_text(strip=True).split("|")[0].strip() if soup.title else ""
        links = []
        for a in soup.find_all("a", href=True):
            nxt = urljoin(resp.url, a["href"].strip())
            path = urlsplit(nxt).path
            if urlsplit(nxt).netloc != "www.au.com":
                continue
            if path.lower().endswith(".pdf") and ("/guide/manual/" in path or "/torisetsu/pdf/" in path):
                links.append({"href": nxt, "label": a.get_text(" ", strip=True)})
            elif path.startswith(ROOT_PATH) and clean(nxt) not in seen and "/business/" not in path:
                seen.add(clean(nxt))
                queue.append(clean(nxt))
        pages.append({"url": url, "status": 200, "title": crumb, "links": links, "fetched_at": now()})
        print(f"  pages {len(pages)}, queue {len(queue)}, pdf here {len(links)}", flush=True)
    write_jsonl(PAGES, pages)
    print(f"pages {len(pages)}, pdf links {sum(len(p['links']) for p in pages)}")


def model_of(url: str) -> str:
    m = MODEL_DIR.search(url) or TORISETSU_DIR.search(urlsplit(url).path)
    return m.group(1).upper() if m else ""


def catalog(_: argparse.Namespace) -> None:
    models = {model_of(l["href"]) for p in load_jsonl(PAGES) for l in p.get("links", [])} - {""}
    known = {squash(m): m for m in models}
    found, pages = scan_catalog(client(), [f"{SITE}/mobile/product/"], ("/mobile/product/",), known, max_pages=300)
    CURRENT.write_text(json.dumps({"models": sorted(found), "pages": pages}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"current {len(found)} of {len(models)} (catalog pages {pages})")


SIZE = re.compile(r"\s*\(\s*[\d.,]+\s*[KMG]B\s*\)\s*$", re.I)


def build(_: argparse.Namespace) -> None:
    c = client()
    current = set(json.loads(CURRENT.read_text(encoding="utf-8"))["models"]) if CURRENT.exists() else set()
    rows, anomalies, stats, seen = [], [], Counter(), set()
    for p in load_jsonl(PAGES):
        kind = urlsplit(p["url"]).path[len(ROOT_PATH):].split("/")[0]
        for l in p.get("links", []):
            model = model_of(l["href"])
            if (model, l["href"]) in seen:
                continue
            seen.add((model, l["href"]))
            if not model:
                anomalies.append({"type": "model_not_in_path", "model": "", "detail": l["label"], "url": l["href"]})
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": kind, "model_raw": model,
                "model_normalized": squash(model), "title": SIZE.sub("", l["label"]), "url": l["href"], "url_type": "pdf",
                "source_method": "crawl", "first_seen": "", "http_status": "", "checked_at": "",
                "model_unconfirmed": "0" if model else "1", "discontinued": "0" if model in current else "",
            })
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    write_rows(ROWS, rows)
    write_anomalies(ANOMALIES, anomalies)
    stats.update(rows=len(rows), unique_urls=len({r["url"] for r in rows}),
                 models_with_manual=len({r["model_raw"] for r in rows if r["model_raw"]}),
                 current_rows=sum(r["discontinued"] == "0" for r in rows))
    stats.update({f"anomaly_{k}": v for k, v in Counter(a["type"] for a in anomalies).items()})
    stats.update({f"http_{k or 'blank'}": v for k, v in Counter(r["http_status"] for r in rows).items()})
    summary = {"stats": dict(sorted(stats.items())), "titles_top": Counter(r["title"] for r in rows).most_common(20)}
    (RAW / f"{KEY}_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    sub.add_parser("crawl").set_defaults(func=crawl)
    sub.add_parser("catalog").set_defaults(func=catalog)
    sub.add_parser("build").set_defaults(func=build)
    args = p.parse_args()
    NOTES.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()

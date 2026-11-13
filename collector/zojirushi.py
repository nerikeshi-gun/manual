"""象印（www.zojirushi.co.jp/toiawase/manual/）の取説URL収集。

API・サイトマップが無いため、取説コーナー（/toiawase/manual/ 配下）だけを同一ドメイン内で巡回する。

    python -m collector.zojirushi listings          # 一覧ページを巡回し、機種ページと生産終了の区分を集める
    python -m collector.zojirushi fetch --phase current|rest
    python -m collector.zojirushi build
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from collections import Counter, defaultdict, deque
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from collector.common import (LOGS, NOTES, RAW, check_urls, decode, load_jsonl, now, run_parallel, squash,
                              write_anomalies, write_jsonl, write_rows)
from collector.polite import PoliteClient, RobotsDisallowed

SITE = "https://www.zojirushi.co.jp"
ROOT_PATH = "/toiawase/manual/"
MAKER, DOMAIN, KEY = "象印", "家電", "zojirushi"
SERIES, PAGES = RAW / f"{KEY}_series.jsonl", RAW / f"{KEY}_pages.jsonl"
ROWS, ANOMALIES = RAW / f"{KEY}_manuals.csv", RAW / f"{KEY}_anomalies.csv"
_client: PoliteClient | None = None


def client() -> PoliteClient:
    global _client
    if _client is None:
        _client = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    return _client


def clean(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def is_listing(path: str) -> bool:
    """カテゴリ一覧（/toiawase/manual/kitchen/ など）か。機種ページは英数字とハイフンのスラッグ。"""
    rest = path[len(ROOT_PATH):].strip("/")
    return rest == "" or not re.search(r"\d", rest.split("/")[-1])


def listings(_: argparse.Namespace) -> None:
    """一覧ページを巡回する。生産終了はカテゴリ単位（「食器洗い乾燥機（生産終了）」）でしか表示されないため、
    生産終了と書かれたカテゴリ一覧に載っている機種ページを生産終了とみなす。"""
    c = client()
    start = SITE + ROOT_PATH
    queue, flags = deque([start]), {start: False}
    series: dict[str, dict] = {}
    pages = 0
    while queue:
        url = queue.popleft()
        try:
            resp = c.get(url)
        except (RobotsDisallowed, requests.RequestException):
            continue
        if resp.status_code != 200:
            continue
        pages += 1
        soup = BeautifulSoup(decode(resp), "lxml")
        crumb = soup.title.get_text(strip=True).split("｜")[0] if soup.title else ""
        for a in soup.find_all("a", href=True):
            nxt = clean(urljoin(resp.url, a["href"]))
            path = urlsplit(nxt).path
            if (urlsplit(nxt).netloc != "www.zojirushi.co.jp" or not path.startswith(ROOT_PATH)
                    or "/search" in path or "/help_product-no/" in path or nxt.rstrip("/") == url.rstrip("/")):
                continue
            if is_listing(path):
                flagged = "生産終了" in a.get_text()
                if nxt not in flags:
                    flags[nxt] = flagged
                    queue.append(nxt)
                else:
                    flags[nxt] = flags[nxt] or flagged
                continue
            rec = series.setdefault(nxt, {"url": nxt, "label": a.get_text(" ", strip=True), "category": crumb,
                                          "found_in": []})
            rec["found_in"].append(url)
        print(f"  listing pages {pages}, series {len(series)}", flush=True)
    for rec in series.values():
        rec["discontinued_listed"] = any(flags.get(u) for u in rec["found_in"])
        rec["category"] = next((u for u in rec["found_in"] if u != start), rec["category"])
    write_jsonl(SERIES, series.values())
    print(json.dumps({"listing_pages": pages, "series": len(series),
                      "discontinued_categories": sorted(u for u, f in flags.items() if f),
                      "current": sum(not s["discontinued_listed"] for s in series.values())}, ensure_ascii=False))


def parse(html: str, base: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True).split("｜")[0] if soup.title else ""
    main = soup.find("main") or soup
    links = []
    for a in main.find_all("a", href=True):
        href = urljoin(base, a["href"].strip())
        if urlsplit(href).path.lower().endswith(".pdf"):
            links.append({"href": href, "label": a.get_text(" ", strip=True)})
    h1 = soup.find("h1")
    return {"title": title, "h1": h1.get_text(" ", strip=True) if h1 else "", "links": links}


def fetch(args: argparse.Namespace) -> None:
    c = client()
    series = load_jsonl(SERIES)
    done = {p["url"] for p in load_jsonl(PAGES) if p["status"] in (200, 404, "robots")}
    chosen = [s for s in series if s["discontinued_listed"] == (args.phase == "rest")]
    todo = [s for s in chosen if s["url"] not in done]
    print(f"phase {args.phase}: {len(chosen)} series pages, to fetch {len(todo)}", flush=True)
    lock = threading.Lock()

    def one(s):
        try:
            resp = c.get(s["url"])
        except RobotsDisallowed:
            rec = {"url": s["url"], "status": "robots", "links": []}
        except requests.RequestException as exc:
            print(f"network error {s['url']}: {type(exc).__name__}", flush=True)
            time.sleep(15)
            return None
        else:
            if resp.status_code in (403, 429) or resp.status_code >= 500:
                time.sleep(60)
                return "blocked"
            rec = {"url": s["url"], "status": resp.status_code,
                   **(parse(decode(resp), resp.url) if resp.status_code == 200 else {"links": []}), "fetched_at": now()}
        with lock, PAGES.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return None

    run_parallel(todo, one)
    print("fetch complete", flush=True)


MODEL = re.compile(r"[A-Z]{1,4}-[A-Z0-9]{2,}(?:-[A-Z0-9]{1,3})?")


def models_in(title: str) -> list[str]:
    """「NX-AB10/NX-AB18（圧力IH炊飯ジャー）」→ ["NX-AB10", "NX-AB18"]。省略形（/AB18）は推測で補わない。"""
    head = re.split(r"[（(]", title)[0]
    return MODEL.findall(head.upper())


def build(_: argparse.Namespace) -> None:
    c = client()
    meta = {s["url"]: s for s in load_jsonl(SERIES)}
    pages = list({p["url"]: p for p in load_jsonl(PAGES)}.values())
    rows, anomalies, stats = [], [], Counter()
    for p in pages:
        s = meta.get(p["url"], {})
        stats[f"page_status_{p['status']}"] += 1
        if p["status"] != 200 or not p["links"]:
            anomalies.append({"type": "no_manual_links" if p["status"] == 200 else "page_not_200", "model": p.get("title", ""),
                              "detail": p["status"], "url": p["url"]})
            continue
        models = models_in(p.get("title") or p.get("h1") or "")
        if len(models) > 1:
            anomalies.append({"type": "multi_model_page", "model": " ".join(models), "detail": p.get("title"), "url": p["url"]})
        category = re.search(r"[（(]([^）)]+)[）)]", p.get("title", ""))
        for model in models or [""]:
            for l in {l["href"]: l for l in p["links"]}.values():
                rows.append({
                    "maker": MAKER, "domain": DOMAIN, "product_category": category.group(1) if category else s.get("category", ""),
                    "model_raw": model, "model_normalized": re.sub(r"\s+", "", model).upper(),
                    "title": re.sub(r"\s*\[[\d.]+\s*[KMG]B\]\s*$", "", l["label"]), "url": l["href"], "url_type": "pdf",
                    "source_method": "crawl", "first_seen": "", "http_status": "", "checked_at": "",
                    "model_unconfirmed": "0" if model else "1",
                    "discontinued": "1" if s.get("discontinued_listed") else "0",
                })
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    url_models = defaultdict(set)
    for r in rows:
        url_models[r["url"]].add(r["model_raw"])
    for url, ms in url_models.items():
        if len(ms) > 1:
            anomalies.append({"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": url})
    write_rows(ROWS, rows)
    write_anomalies(ANOMALIES, anomalies)
    stats.update(rows=len(rows), pages=len(pages), unique_urls=len({r["url"] for r in rows}),
                 models_with_manual=len({r["model_raw"] for r in rows if r["model_raw"]}),
                 rows_model_unconfirmed=sum(r["model_unconfirmed"] == "1" for r in rows))
    stats.update({f"anomaly_{k}": v for k, v in Counter(a["type"] for a in anomalies).items()})
    stats.update({f"http_{k or 'blank'}": v for k, v in Counter(r["http_status"] for r in rows).items()})
    summary = {"stats": dict(sorted(stats.items())), "titles_top": Counter(r["title"] for r in rows).most_common(20)}
    (RAW / f"{KEY}_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    sub.add_parser("listings").set_defaults(func=listings)
    f = sub.add_parser("fetch")
    f.add_argument("--phase", choices=["current", "rest"], default="current")
    f.set_defaults(func=fetch)
    sub.add_parser("build").set_defaults(func=build)
    args = p.parse_args()
    NOTES.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()

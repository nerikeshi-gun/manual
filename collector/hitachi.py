"""日立（kadenfan.hitachi.co.jp）の取説URL収集。

    python -m collector.hitachi models             # 取説検索の索引 search.json
    python -m collector.hitachi catalog            # 製品カタログを巡回し現行品の型番を特定
    python -m collector.hitachi fetch --phase current|rest
    python -m collector.hitachi build
    python -m collector.hitachi verify
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from collector.common import (LOGS, NOTES, RAW, check_urls, decode, load_jsonl, now, run_parallel, scan_catalog,
                              squash, write_anomalies, write_jsonl, write_rows)
from collector.polite import PoliteClient, RobotsDisallowed

SITE = "https://kadenfan.hitachi.co.jp"
MAKER, DOMAIN, KEY = "日立", "家電", "hitachi"
MODELS, CURRENT, PAGES = RAW / f"{KEY}_models.jsonl", RAW / f"{KEY}_current.json", RAW / f"{KEY}_pages.jsonl"
ROWS, ANOMALIES = RAW / f"{KEY}_manuals.csv", RAW / f"{KEY}_anomalies.csv"
CATALOG_DIRS = ["/air/", "/airclean/", "/bathroom/", "/clean/", "/dehumidifier/", "/futon/", "/hot/", "/ih/", "/iron/",
                "/kankisen/", "/kitchen/", "/kyutou/", "/lighting/", "/pump/", "/ra/", "/range/", "/rei/", "/shaver/",
                "/solar/", "/steamer/", "/toaster/", "/toilet/", "/wash/", "/ziaenso/"]
_client: PoliteClient | None = None


def client() -> PoliteClient:
    global _client
    if _client is None:
        _client = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    return _client


def models(_: argparse.Namespace) -> None:
    items = json.loads(client().get(f"{SITE}/support/manual/search.json").content.decode("utf-8-sig"))["items"]
    out = {}
    for it in items:
        out.setdefault(it["url"], {"model": it["title"], "category": it["productsname"], "url": it["url"],
                                   "rimocon": it.get("rimocon", "")})
    write_jsonl(MODELS, out.values())
    print(f"models {len(out)} (index items {len(items)})")


def catalog(_: argparse.Namespace) -> None:
    known = {squash(m["model"]): m["model"] for m in load_jsonl(MODELS)}
    found_all, report = set(), {}
    for d in CATALOG_DIRS:
        found, pages = scan_catalog(client(), [SITE + d], (d,), known, max_pages=150)
        found_all |= found
        report[d] = {"pages": pages, "models": len(found)}
        print(f"  {d}: pages {pages}, models {len(found)}", flush=True)
    CURRENT.write_text(json.dumps({"models": sorted(found_all), "dirs": report}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"current models {len(found_all)}")


def parse(html: str, base: str) -> tuple[list[dict], bool]:
    soup = BeautifulSoup(html, "lxml")
    main = soup.find(id="Contents") or soup.find(id="body") or soup
    links = []
    for a in main.find_all("a", href=True):
        href = urljoin(base, a["href"].strip())
        if urlsplit(href).path.lower().endswith(".pdf") and "/support/about/" not in href:
            links.append({"href": href, "label": a.get_text(" ", strip=True)})
    text = soup.get_text(" ", strip=True)
    return links, any(k in text for k in ("生産終了", "生産完了", "販売終了"))


def fetch(args: argparse.Namespace) -> None:
    c = client()
    allm = load_jsonl(MODELS)
    current = set(json.loads(CURRENT.read_text(encoding="utf-8"))["models"]) if CURRENT.exists() else set()
    done = {p["url"] for p in load_jsonl(PAGES) if p["status"] in (200, 404, "robots")}
    chosen = [m for m in allm if (m["model"] in current) == (args.phase == "current")]
    todo = [m for m in chosen if m["url"] not in done]
    print(f"phase {args.phase}: {len(chosen)} models, to fetch {len(todo)}", flush=True)
    lock = threading.Lock()

    def one(m):
        try:
            resp = c.get(SITE + m["url"])
        except RobotsDisallowed:
            rec = {"url": m["url"], "model": m["model"], "status": "robots", "links": []}
        except requests.RequestException as exc:
            print(f"network error {m['model']}: {type(exc).__name__}", flush=True)
            time.sleep(15)
            return None
        else:
            if resp.status_code in (403, 429) or resp.status_code >= 500:
                print(f"status {resp.status_code} on {m['model']}", flush=True)
                time.sleep(60)
                return "blocked"
            links, disc = parse(decode(resp), resp.url) if resp.status_code == 200 else ([], False)
            rec = {"url": m["url"], "model": m["model"], "status": resp.status_code, "links": links,
                   "discontinued_shown": disc, "fetched_at": now()}
        with lock, PAGES.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return None

    run_parallel(todo, one)
    print("fetch complete", flush=True)


def normalize(model: str) -> str:
    """NFKC・大文字化。日立の索引型番には色記号が付かないため除去はしない。"""
    import unicodedata
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", model)).upper()


def build(_: argparse.Namespace) -> None:
    c = client()
    meta = {m["url"]: m for m in load_jsonl(MODELS)}
    current = set(json.loads(CURRENT.read_text(encoding="utf-8"))["models"]) if CURRENT.exists() else set()
    pages = list({p["url"]: p for p in load_jsonl(PAGES)}.values())
    url_models = defaultdict(set)
    for p in pages:
        for l in p.get("links", []):
            url_models[l["href"]].add(p["model"])
    rows, anomalies, stats = [], [], Counter()
    for p in pages:
        stats[f"page_status_{p['status']}"] += 1
        if p["status"] != 200:
            anomalies.append({"type": "page_not_200", "model": p["model"], "detail": p["status"], "url": SITE + p["url"]})
            continue
        if not p["links"]:
            anomalies.append({"type": "no_manual_links", "model": p["model"], "detail": "", "url": SITE + p["url"]})
            continue
        for l in {l["href"]: l for l in p["links"]}.values():
            fname = urlsplit(l["href"]).path.rsplit("/", 1)[-1]
            if squash(p["model"])[:6].lower() not in squash(fname).lower() and len(url_models[l["href"]]) == 1:
                stats["filename_without_model"] += 1
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": meta.get(p["url"], {}).get("category", ""),
                "model_raw": p["model"], "model_normalized": normalize(p["model"]), "title": l["label"], "url": l["href"],
                "url_type": "pdf", "source_method": "api", "first_seen": "", "http_status": "", "checked_at": "",
                "model_unconfirmed": "0",
                "discontinued": "1" if p.get("discontinued_shown") else ("0" if p["model"] in current else ""),
            })
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    for url, ms in url_models.items():
        if len(ms) > 1:
            anomalies.append({"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": url})
    write_rows(ROWS, rows)
    write_anomalies(ANOMALIES, anomalies)
    stats.update(rows=len(rows), pages=len(pages), unique_urls=len({r["url"] for r in rows}),
                 models_with_manual=len({r["model_raw"] for r in rows}), current_models=len(current))
    stats.update({f"anomaly_{k}": v for k, v in Counter(a["type"] for a in anomalies).items()})
    stats.update({f"http_{k or 'blank'}": v for k, v in Counter(r["http_status"] for r in rows).items()})
    summary = {"stats": dict(sorted(stats.items())), "titles_top": Counter(r["title"] for r in rows).most_common(20)}
    (RAW / f"{KEY}_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    sub.add_parser("models").set_defaults(func=models)
    sub.add_parser("catalog").set_defaults(func=catalog)
    f = sub.add_parser("fetch")
    f.add_argument("--phase", choices=["current", "rest"], default="current")
    f.set_defaults(func=fetch)
    sub.add_parser("build").set_defaults(func=build)
    args = p.parse_args()
    NOTES.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()

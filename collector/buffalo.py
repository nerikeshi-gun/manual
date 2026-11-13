"""バッファロー（www.buffalo.jp）の取説URL収集。

    python -m collector.buffalo models     # サイトマップの「取扱説明書」タブ（/product/detail/manual/<型番>.html）から全型番
    python -m collector.buffalo catalog    # 製品カテゴリ一覧（/product/category/）を巡回し現行品を特定
    python -m collector.buffalo fetch --phase current|rest
    python -m collector.buffalo build

取説一覧は製品ページが呼ぶJSON API（/api/v1/productDetail/manual?item_code=）で取得する。
販売状況は /api/v1/product_item/n?item_code= の status（新商品／販売終了 など）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from urllib.parse import quote, urljoin, urlsplit

import requests

from collector.common import (LOGS, NOTES, RAW, check_urls, load_jsonl, now, run_parallel, scan_catalog, squash,
                              write_anomalies, write_jsonl, write_rows)
from collector.polite import PoliteClient, RobotsDisallowed

SITE = "https://www.buffalo.jp"
MAKER, DOMAIN, KEY = "バッファロー", "通信", "buffalo"
MODELS, CURRENT, PAGES = RAW / f"{KEY}_models.jsonl", RAW / f"{KEY}_current.json", RAW / f"{KEY}_pages.jsonl"
ROWS, ANOMALIES = RAW / f"{KEY}_manuals.csv", RAW / f"{KEY}_anomalies.csv"
_client: PoliteClient | None = None


def client() -> PoliteClient:
    global _client
    if _client is None:
        _client = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    return _client


def models(_: argparse.Namespace) -> None:
    c = client()
    index = re.findall(r"<loc>([^<]+)", c.get(f"{SITE}/sitemap.xml").text)
    found = {}
    for sm in [u for u in index if "sitemap_all_" in u]:
        for loc in re.findall(r"<loc>([^<]+)", c.get(sm).text):
            m = re.match(rf"{re.escape(SITE)}/product/detail/manual/([^/]+)\.html$", loc)
            if m:
                found.setdefault(m.group(1), {"slug": m.group(1), "item_code": m.group(1).upper()})
    write_jsonl(MODELS, found.values())
    print(f"models {len(found)}")


def catalog(_: argparse.Namespace) -> None:
    from bs4 import BeautifulSoup
    from collector.common import decode
    known = {squash(m["item_code"]): m["item_code"] for m in load_jsonl(MODELS)}
    top = BeautifulSoup(decode(client().get(f"{SITE}/")), "lxml")
    seeds = sorted({urljoin(SITE + "/", a["href"]).split("?")[0] for a in top.find_all("a", href=True)
                    if urljoin(SITE + "/", a["href"]).startswith(f"{SITE}/product/category/")})
    found, pages = scan_catalog(client(), seeds, ("/product/category/",), known, max_pages=800,
                                exclude=("/support/", "/product/detail/"))
    CURRENT.write_text(json.dumps({"models": sorted(found), "pages": pages}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"current (listed in catalog) {len(found)} of {len(known)}, pages {pages}")


def fetch(args: argparse.Namespace) -> None:
    c = client()
    current = set(json.loads(CURRENT.read_text(encoding="utf-8"))["models"]) if CURRENT.exists() else set()
    allm = load_jsonl(MODELS)
    done = {p["item_code"] for p in load_jsonl(PAGES) if p["status"] in (200, 404, "robots")}
    if args.phase == "all":  # 現行品を事前に絞れないため、全型番を取りながら販売状況で判定する
        chosen = allm
    else:
        chosen = [m for m in allm if (m["item_code"] in current) == (args.phase == "current")]
    todo = [m for m in chosen if m["item_code"] not in done]
    print(f"phase {args.phase}: {len(chosen)} models, to fetch {len(todo)}", flush=True)
    lock = threading.Lock()

    def one(m):
        code = quote(m["item_code"], safe="")
        try:
            man = c.get(f"{SITE}/api/v1/productDetail/manual?item_code={code}")
            item = c.get(f"{SITE}/api/v1/product_item/n?item_code={code}")
        except RobotsDisallowed:
            rec = {"item_code": m["item_code"], "status": "robots", "links": []}
        except requests.RequestException as exc:
            print(f"network error {m['item_code']}: {type(exc).__name__}", flush=True)
            time.sleep(15)
            return None
        else:
            if man.status_code in (403, 429) or man.status_code >= 500:
                time.sleep(60)
                return "blocked"
            try:
                docs = man.json().get("result_list") or []
                info = (item.json().get("result_list") or [{}])[0]
            except ValueError:
                docs, info = [], {}
            rec = {"item_code": m["item_code"], "status": man.status_code, "sale_status": info.get("status", ""),
                   "series": info.get("series_code", ""),
                   "links": [{"href": d.get("downloadUrl") or urljoin(SITE, d.get("linkUrl", "")), "label": d.get("linkText", ""),
                              "type": d.get("type", ""), "updated": d.get("updated", ""), "tos": d.get("tosPattern", ""),
                              "private_group": d.get("private_group", "")} for d in docs],
                   "fetched_at": now()}
        with lock, PAGES.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return None

    run_parallel(todo, one)
    print("fetch complete", flush=True)


def build(_: argparse.Namespace) -> None:
    c = client()
    current = set(json.loads(CURRENT.read_text(encoding="utf-8"))["models"]) if CURRENT.exists() else set()
    pages = list({p["item_code"]: p for p in load_jsonl(PAGES)}.values())
    rows, anomalies, stats = [], [], Counter()
    for p in pages:
        stats[f"sale_status_{p.get('sale_status') or 'unknown'}"] += 1
        docs = [d for d in p.get("links", []) if d["href"] and not d.get("private_group")]
        if not docs:
            anomalies.append({"type": "no_manual_links", "model": p["item_code"], "detail": p.get("sale_status", ""), "url": ""})
            continue
        for d in {d["href"]: d for d in docs}.values():
            path = urlsplit(d["href"]).path.lower()
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": p.get("series", ""), "model_raw": p["item_code"],
                "model_normalized": p["item_code"].upper(), "title": re.sub(r"\s*\((PDF|HTML)\)\s*$", "", d["label"]),
                "url": d["href"], "url_type": "pdf" if path.endswith(".pdf") else "html", "source_method": "api",
                "first_seen": "", "http_status": "", "checked_at": "", "model_unconfirmed": "0",
                "discontinued": "1" if p.get("sale_status") == "販売終了" else ("0" if p.get("sale_status") or p["item_code"] in current else ""),
            })
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    url_models = defaultdict(set)
    for r in rows:
        url_models[r["url"]].add(r["model_raw"])
    anomalies += [{"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": u}
                  for u, ms in url_models.items() if len(ms) > 1]
    write_rows(ROWS, rows)
    write_anomalies(ANOMALIES, anomalies)
    stats.update(rows=len(rows), pages=len(pages), unique_urls=len(url_models),
                 models_with_manual=len({r["model_raw"] for r in rows}))
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
    f.add_argument("--phase", choices=["current", "rest", "all"], default="current")
    f.set_defaults(func=fetch)
    sub.add_parser("build").set_defaults(func=build)
    args = p.parse_args()
    NOTES.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()

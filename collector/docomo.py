"""ドコモ（www.docomo.ne.jp/support/manual/）の取説URL収集。

    python -m collector.docomo models     # 取説検索API（カテゴリ×シリーズ）で全機種
    python -m collector.docomo catalog    # 製品ラインナップ（/product/）を巡回し現行機種を特定
    python -m collector.docomo fetch --phase current|rest
    python -m collector.docomo build

各機種ページの「ご利用条件」に同意（download.html へ a=manualDownloadLink をPOST）すると取説PDFの一覧が出る。
規約への同意はユーザーの承認済み（2026-11-13、同種の規約を含む）。同意はセッション単位なのでスレッドごとにセッションを分ける。
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

from collector.common import (LOGS, NOTES, RAW, check_urls, decode, load_jsonl, now, run_parallel, scan_catalog,
                              squash, write_anomalies, write_jsonl, write_rows)
from collector.polite import PoliteClient, RobotsDisallowed

SITE = "https://www.docomo.ne.jp"
API = f"{SITE}/js/support/common/api/"
MAKER, DOMAIN, KEY = "ドコモ", "通信", "docomo"
MODELS, CURRENT, PAGES = RAW / f"{KEY}_models.jsonl", RAW / f"{KEY}_current.json", RAW / f"{KEY}_pages.jsonl"
ROWS, ANOMALIES = RAW / f"{KEY}_manuals.csv", RAW / f"{KEY}_anomalies.csv"
CATEGORIES = {
    "android_smartphone": "Android スマートフォン", "pixel": "Google Pixel", "tablet": "Android タブレット",
    "imode_phone": "ドコモ ケータイ", "raku_foma": "らくらくホン・あんしんスマホ", "kids_junior": "キッズ・ジュニア",
    "nexus": "Nexus", "one_number": "ワンナンバーサービス対応製品", "drivers_support": "ドライバーズサポート対応製品",
    "data_card": "データ通信製品", "bookreader": "ブックリーダー", "photoframe": "デジタルフォトフレーム",
    "option": "docomo select", "5g_home_router": "5G対応ホームルーター", "chromebook_pc": "Chromebook / パソコン",
    "landline_service": "固定電話サービス対応製品",
}
HEADERS = {"Content-Type": "application/x-www-form-urlencoded", "Referer": f"{SITE}/support/manual/",
           "X-Requested-With": "XMLHttpRequest"}
_client: PoliteClient | None = None


def client() -> PoliteClient:
    global _client
    if _client is None:
        _client = PoliteClient(log_path=LOGS / f"{KEY}_requests.log", session_per_thread=True)
    return _client


def api(endpoint: str, params: str) -> str:
    return decode(client().post(API + endpoint, data="type=mdj&" + params, headers=HEADERS))


def parse_models(text: str) -> list[dict]:
    body = re.search(r"models:\[(.*?)\]\}", text, re.S)
    if not body:
        return []
    out = []
    for item in re.finditer(r"\{([^{}]*)\}", body.group(1)):
        fields = dict(re.findall(r'(\w+):"([^"]*)"', item.group(1)))
        if fields.get("ua"):
            out.append(fields)
    return out


def models(_: argparse.Namespace) -> None:
    found: dict[str, dict] = {}
    for cat, label in CATEGORIES.items():
        first = api("get_result_by_category.php", f"category={cat}")
        listed = parse_models(first)
        series = re.search(r"series:\[([^\]]*)\]", first)
        names = re.findall(r'"([^"]+)"', series.group(1)) if series else []
        for s in names:
            listed += [dict(m, series=m.get("series") or s) for m in parse_models(api("get_result_by_pulldown.php", f"category={cat}&series={s}"))]
        for m in listed:
            found.setdefault(m["ua"].lower(), {"ua": m["ua"].lower(), "name": m.get("name", ""), "series": m.get("series", ""),
                                               "category": label})
        print(f"  {cat}: series {len(names)}, total {len(found)}", flush=True)
    write_jsonl(MODELS, sorted(found.values(), key=lambda m: m["series"], reverse=True))
    print(f"models {len(found)}")


def catalog(_: argparse.Namespace) -> None:
    known = {squash(m["ua"]): m["ua"] for m in load_jsonl(MODELS)}
    found, pages = scan_catalog(client(), [f"{SITE}/product/"], ("/product/",), known, max_pages=400)
    CURRENT.write_text(json.dumps({"models": sorted(found), "pages": pages}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"current {len(found)} (catalog pages {pages})")


def parse(html: str, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"].strip())
        if urlsplit(href).path.lower().endswith(".pdf") and "/manual/" in href and href not in seen:
            seen.add(href)
            out.append({"href": href, "label": a.get_text(" ", strip=True)})
    return out


def fetch(args: argparse.Namespace) -> None:
    c = client()
    current = set(json.loads(CURRENT.read_text(encoding="utf-8"))["models"]) if CURRENT.exists() else set()
    allm = load_jsonl(MODELS)
    done = {p["ua"] for p in load_jsonl(PAGES) if p["status"] in (200, 404, "robots")}
    chosen = [m for m in allm if (m["ua"] in current) == (args.phase == "current")]
    todo = [m for m in chosen if m["ua"] not in done]
    print(f"phase {args.phase}: {len(chosen)} models, to fetch {len(todo)}", flush=True)
    lock = threading.Lock()

    def one(m):
        index = f"{SITE}/support/manual/{m['ua']}/index.html"
        try:
            first = c.get(index)
            if first.status_code == 200:
                resp = c.post(f"{SITE}/support/manual/{m['ua']}/download.html", data={"a": "manualDownloadLink"},
                              headers={"Referer": index, "Origin": SITE}, allow_redirects=False)  # 「同意する」
            else:
                resp = first
        except RobotsDisallowed:
            rec = {"ua": m["ua"], "status": "robots", "links": []}
        except requests.RequestException as exc:
            print(f"network error {m['ua']}: {type(exc).__name__}", flush=True)
            time.sleep(15)
            return None
        else:
            if resp.status_code in (403, 429) or resp.status_code >= 500:
                time.sleep(60)
                return "blocked"
            rec = {"ua": m["ua"], "status": resp.status_code,
                   "links": parse(decode(resp), f"{SITE}/support/manual/{m['ua']}/") if resp.status_code == 200 else [],
                   "fetched_at": now()}
        with lock, PAGES.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return None

    run_parallel(todo, one)
    print("fetch complete", flush=True)


MODEL_IN_NAME = re.compile(r"([A-Z]{1,3}-\d{2}[A-Z])\s*$")


def build(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    meta = {m["ua"]: m for m in load_jsonl(MODELS)}
    current = set(json.loads(CURRENT.read_text(encoding="utf-8"))["models"]) if CURRENT.exists() else set()
    pages = list({p["ua"]: p for p in load_jsonl(PAGES)}.values())
    rows, anomalies, stats = [], [], Counter()
    for p in pages:
        m = meta.get(p["ua"], {})
        stats[f"page_status_{p['status']}"] += 1
        if p["status"] != 200 or not p["links"]:
            anomalies.append({"type": "no_manual_links" if p["status"] == 200 else "page_not_200", "model": p["ua"],
                              "detail": p["status"], "url": f"{SITE}/support/manual/{p['ua']}/index.html"})
            continue
        shown = MODEL_IN_NAME.search(m.get("name", ""))
        model_raw = shown.group(1) if shown else m.get("name") or p["ua"].upper()
        for l in p["links"]:
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": m.get("category", ""), "model_raw": model_raw,
                "model_normalized": squash(model_raw) if shown else p["ua"].upper(), "title": l["label"], "url": l["href"],
                "url_type": "pdf", "source_method": "api", "first_seen": "", "http_status": "", "checked_at": "",
                "model_unconfirmed": "0", "discontinued": "0" if p["ua"] in current else "",
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

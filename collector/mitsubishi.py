"""三菱電機（WIN2K: www.mitsubishielectric.co.jp/ldg/wink/）の取説URL収集。

    python -m collector.mitsubishi models --current   # 現行品のみ（oldProductFlg=0）
    python -m collector.mitsubishi models             # 生産終了品も含む（oldProductFlg=1）
    python -m collector.mitsubishi fetch
    python -m collector.mitsubishi build
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from collector.common import (LOGS, NOTES, RAW, check_urls, decode, load_jsonl, now, run_parallel, squash,
                              write_anomalies, write_jsonl, write_rows)
from collector.polite import PoliteClient, RobotsDisallowed

SITE = "https://www.mitsubishielectric.co.jp"
WINK = f"{SITE}/ldg/wink/ssl/"
MAKER, DOMAIN, KEY = "三菱電機", "家電", "mitsubishi"
MODELS, PAGES = RAW / f"{KEY}_models.jsonl", RAW / f"{KEY}_pages.jsonl"
ROWS, ANOMALIES = RAW / f"{KEY}_manuals.csv", RAW / f"{KEY}_anomalies.csv"
DATE = re.compile(r"(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?")
DOC_WORDS = ("説明書", "ガイド", "マニュアル")
_client: PoliteClient | None = None


def client() -> PoliteClient:
    global _client
    if _client is None:
        _client = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    return _client


def ymd(text: str) -> str:
    m = DATE.search(text or "")
    if not m:
        return ""
    return f"{m.group(1)}-{int(m.group(2)):02d}" + (f"-{int(m.group(3)):02d}" if m.group(3) else "")


def categories() -> dict[str, str]:
    """サポートページの「取扱説明書ダウンロード」リンクから家電の製品分類コードを集める。"""
    soup = BeautifulSoup(decode(client().get(f"{SITE}/support/")), "lxml")
    cats = {}
    for a in soup.find_all("a", href=True):
        m = re.search(r"searchProduct\.do\?ccd=(\d+)[^#]*mcid=TORISETSU", a["href"])
        if m:
            heading = a.find_previous(["h2", "h3", "h4"])
            cats.setdefault(m.group(1), heading.get_text(" ", strip=True) if heading else "")
    return cats


def models(args: argparse.Namespace) -> None:
    c = client()
    cats = categories()
    print(f"categories {len(cats)}", flush=True)
    existing = {m["pid"]: m for m in load_jsonl(MODELS)}
    flg = "0" if args.current else "1"
    for ccd, label in cats.items():
        page, seen_here = 1, 0
        while True:
            url = (f"{WINK}searchProductResult.do?ccd={ccd}&releaseFrom=&releaseTo=&oldProductFlg={flg}&contentsList=2"
                   f"&pn=&pns=&pnsCsv=&kwd=&pageNo={page}&log=false&showAll=true&init={'true' if page == 1 else 'false'}")
            soup = BeautifulSoup(decode(c.get(url)), "lxml")
            added = 0
            for a in soup.find_all("a", href=re.compile(r"displayProduct\.do\?pid=\d+&ccd=\d+$")):
                name = a.get_text(" ", strip=True)
                if not name:
                    continue
                q = parse_qs(urlsplit(a["href"]).query)
                row = a.find_parent("tr") or a.find_parent("li") or a.parent
                text = row.get_text(" ", strip=True) if row else ""
                end = re.search(r"生産終了[:：]\s*(\d{4}年\d{1,2}月(?:\d{1,2}日)?)?", text)
                rec = existing.setdefault(q["pid"][0], {"pid": q["pid"][0], "ccd": q["ccd"][0], "model": name})
                rec.update({"category": rec.get("category") or label, "release": ymd(text.split("生産終了")[0]),
                            "production_end": ymd(end.group(1)) if end and end.group(1) else ""})
                if flg == "0":
                    rec["current_listed"] = True
                added += 1
            seen_here += added
            nxt = soup.find("a", attrs={"number": str(page + 1)})
            if not added or not nxt:
                break
            page += 1
        print(f"  {ccd} {label}: {seen_here}", flush=True)
    write_jsonl(MODELS, sorted(existing.values(), key=lambda m: m.get("release", ""), reverse=True))
    print(f"models {len(existing)}, current {sum(bool(m.get('current_listed')) for m in existing.values())}")


def parse(html: str, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"].strip())
        label = a.get_text(" ", strip=True)
        path = urlsplit(href).path.lower()
        if not path.endswith(".pdf") or "/wink_doc/" not in path or "free_parts" in path or "hoyubhnlist" in path:
            continue
        section = a.find_previous(attrs={"id": re.compile(r"^[A-Z_]{4,}$")})
        sec = section.get("id") if section else ""
        if sec in ("TORISETSU", "SUETSUKE", "KOUJI") or any(w in label for w in DOC_WORDS):
            links.append({"href": href, "label": label, "section": sec})
    return links


def fetch(args: argparse.Namespace) -> None:
    c = client()
    allm = load_jsonl(MODELS)
    done = {p["pid"] for p in load_jsonl(PAGES) if p["status"] in (200, 404, "robots")}
    chosen = [m for m in allm if m.get("current_listed")] if args.current else allm
    todo = [m for m in chosen if m["pid"] not in done]
    print(f"{'current' if args.current else 'all'}: {len(chosen)} models, to fetch {len(todo)}", flush=True)
    lock = threading.Lock()

    def one(m):
        try:
            resp = c.get(f"{WINK}displayProduct.do?pid={m['pid']}&ccd={m['ccd']}")
        except RobotsDisallowed:
            rec = {"pid": m["pid"], "model": m["model"], "status": "robots", "links": []}
        except requests.RequestException as exc:
            print(f"network error {m['model']}: {type(exc).__name__}", flush=True)
            time.sleep(15)
            return None
        else:
            if resp.status_code in (403, 429) or resp.status_code >= 500:
                print(f"status {resp.status_code} on {m['model']}", flush=True)
                time.sleep(60)
                return "blocked"
            rec = {"pid": m["pid"], "model": m["model"], "status": resp.status_code,
                   "links": parse(decode(resp), resp.url) if resp.status_code == 200 else [], "fetched_at": now()}
        with lock, PAGES.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return None

    run_parallel(todo, one)
    print("fetch complete", flush=True)


def normalize(model: str) -> str:
    import unicodedata
    value = re.sub(r"\s+", "", unicodedata.normalize("NFKC", model)).upper()
    m = re.search(r"-([A-Z]{1,2})$", value)  # MR-P14N-B の -B（色）
    return value[: m.start()] if m and len(value) - len(m.group(0)) >= 5 else value


def build(_: argparse.Namespace) -> None:
    c = client()
    meta = {m["pid"]: m for m in load_jsonl(MODELS)}
    pages = list({p["pid"]: p for p in load_jsonl(PAGES)}.values())
    url_models = defaultdict(set)
    for p in pages:
        for l in p.get("links", []):
            url_models[l["href"]].add(p["model"])
    rows, anomalies, stats = [], [], Counter()
    for p in pages:
        m = meta.get(p["pid"], {})
        stats[f"page_status_{p['status']}"] += 1
        if p["status"] != 200 or not p["links"]:
            anomalies.append({"type": "no_manual_links" if p["status"] == 200 else "page_not_200", "model": p["model"],
                              "detail": p["status"], "url": f"{WINK}displayProduct.do?pid={p['pid']}"})
            continue
        for l in {l["href"]: l for l in p["links"]}.values():
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": m.get("category", ""),
                "model_raw": p["model"], "model_normalized": normalize(p["model"]), "title": re.sub(r"\s*\(\s*[\d.,]+\s*[KMG]?B\s*\)\s*$", "", re.sub(r"\s+", " ", l["label"]).strip()), "url": l["href"],
                "url_type": "pdf", "source_method": "crawl", "first_seen": "", "http_status": "", "checked_at": "",
                "model_unconfirmed": "0",
                "discontinued": "1" if m.get("production_end") else ("0" if m.get("current_listed") else ""),
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
    m = sub.add_parser("models")
    m.add_argument("--current", action="store_true")
    m.set_defaults(func=models)
    f = sub.add_parser("fetch")
    f.add_argument("--current", action="store_true")
    f.set_defaults(func=fetch)
    sub.add_parser("build").set_defaults(func=build)
    args = p.parse_args()
    NOTES.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()

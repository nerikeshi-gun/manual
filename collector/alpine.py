"""アルパイン（products.alpine.co.jp/om/）の取説URL収集。

取説トップ（/om/owner/top）は「サーバが混雑しております」を返し続ける（2026-11-13, 11-14 とも）が、
検索 /om/owner/search?P0=<page>&P1=<キーワード> と製品別ページ /om/owner/product?P1=<id> は表示できる。
- 列挙: キーワード空の検索で全製品（発売の新しい順、10件/ページ）
- 販売終了: www.alpine.co.jp/archives（過去の製品一覧）に載る P1。phase current = 載らないもの、rest = 載るもの

製品ページは製品構成ごとに div.detailContents（h4 = 型番、表の th = 「資料名：ファイル名」、
リンク = owner/dl?P1=&P2=、application/octet-stream で PDF を返す）。

    python -m collector.alpine run --phase current|rest
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

WWW = "https://www.alpine.co.jp"
OM = "https://products.alpine.co.jp/om/"
MAKER, DOMAIN, KEY = "アルパイン", "車載", "alpine"
PAGES = RAW / f"{KEY}_pages.jsonl"
P1 = re.compile(r"products\.alpine\.co\.jp/om/owner/product\?P1=(\d+)")


MODELS = RAW / f"{KEY}_models.jsonl"


def listing(c: PoliteClient) -> list[dict]:
    """取説システムの検索（キーワード空）で全製品を発売の新しい順に列挙。1ページ10件。
    www.alpine.co.jp/archives（過去の製品一覧）に載る P1 を販売終了品とする。"""
    archived = set(P1.findall(decode(c.get(f"{WWW}/archives"))))
    out, page, last = [], 1, 1
    while page <= last:
        soup = BeautifulSoup(decode(c.get(f"{OM}owner/search", params={"P0": str(page), "P1": ""})), "lxml")
        for a in soup.find_all("a", href=True):
            m = re.search(r"P0=(\d+)", a["href"])
            if "search" in a["href"] and m:
                last = max(last, int(m.group(1)))
        for a in soup.select(".resultList a[href*='product?P1=']"):
            pid = re.search(r"P1=(\d+)", a["href"]).group(1)
            h4, p = a.find("h4"), a.find("p")
            text = p.get_text(" ", strip=True) if p else ""
            rel = re.search(r"発売時期：\s*(\d{4})年(\d{1,2})月", text)
            out.append({"P1": pid, "model": h4.get_text(strip=True) if h4 else "",
                        "name": re.sub(r"\s*発売時期：.*$", "", text), "release": f"{rel.group(1)}-{int(rel.group(2)):02d}" if rel else "",
                        "rank": len(out) + 1, "archived": pid in archived})
        if page % 20 == 0:
            print(f"  search page {page}/{last}: {len(out)}", flush=True)
        page += 1
    return out


def parse(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    det = soup.select_one(".productDetail")
    info = {}
    if det:
        h3 = det.find("h3")
        info["set_title"] = h3.get_text(" ", strip=True) if h3 else ""
        for tr in det.find_all("tr"):
            th, td = tr.find("th"), tr.find("td")
            if th and td:
                info[th.get_text(strip=True)] = td.get_text(" ", strip=True).lstrip(":").strip()
    parts = []
    for block in soup.select("div.detailContents"):
        h4 = block.find("h4")
        desc = block.select_one(".setTitle p")
        links = []
        for tr in block.find_all("tr"):
            a = tr.find("a", href=re.compile(r"owner/dl\?"))
            th = tr.find("th")
            if a and th:
                links.append({"href": urljoin(OM + "owner/", a["href"]), "label": th.get_text(" ", strip=True)})
        parts.append({"model": h4.get_text(" ", strip=True) if h4 else "", "desc": desc.get_text(" ", strip=True) if desc else "",
                      "links": links})
    return {"info": info, "parts": parts, "busy": "混雑しております" in html}


def run(args: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    if not MODELS.exists():
        write_jsonl(MODELS, listing(c))
    models = load_jsonl(MODELS)
    want_archived = args.phase == "rest"
    ids = {m["P1"]: m.get("release", "") for m in models if m["archived"] == want_archived}
    done = {p["P1"] for p in load_jsonl(PAGES) if p["status"] == 200 and not p.get("busy")}
    todo = [(pid, cat) for pid, cat in ids.items() if pid not in done]
    print(f"phase {args.phase}: P1 {len(ids)}, to fetch {len(todo)}", flush=True)
    lock = threading.Lock()

    def one(item):
        pid, release = item
        cat = ""
        url = f"{OM}owner/product?P1={pid}"
        try:
            resp = c.get(url)
        except (RobotsDisallowed, requests.RequestException) as exc:
            print(f"error {url}: {type(exc).__name__}", flush=True)
            return None
        if resp.status_code in (403, 429) or resp.status_code >= 500:
            time.sleep(60)
            return "blocked"
        rec = {"P1": pid, "cat": cat, "release": release, "phase": args.phase, "status": resp.status_code, "url": url,
               **parse(decode(resp)), "fetched_at": now()}
        with lock, PAGES.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return None

    run_parallel(todo, one)
    build(c)


LABEL = re.compile(r"^(.*?)[：:]\s*[\w.\-]+\.pdf\s*$", re.I)


def build(c: PoliteClient) -> None:
    pages = {}
    for p in load_jsonl(PAGES):  # current を優先（同じ P1 が両方に出る場合）
        if p["P1"] not in pages or p["phase"] == "current":
            pages[p["P1"]] = p
    rows, anomalies, stats = [], [], Counter()
    for p in pages.values():
        if p["status"] != 200 or p.get("busy"):
            anomalies.append({"type": "page_not_ok", "model": p["P1"], "detail": "busy" if p.get("busy") else p["status"], "url": p["url"]})
            continue
        if not any(part["links"] for part in p["parts"]):
            anomalies.append({"type": "no_manual_links", "model": p["info"].get("製品名", ""), "detail": p["P1"], "url": p["url"]})
            continue
        for part in p["parts"]:
            model = part["model"] or p["info"].get("製品名", "")
            for l in {l["href"]: l for l in part["links"]}.values():
                m = LABEL.match(l["label"])
                rows.append({
                    "maker": MAKER, "domain": DOMAIN, "product_category": p["cat"], "model_raw": model,
                    "model_normalized": squash(model), "title": (m.group(1) if m else l["label"]).strip(),
                    "url": l["href"], "url_type": "pdf", "source_method": "crawl", "first_seen": "",
                    "http_status": "", "checked_at": "", "model_unconfirmed": "0" if model else "1",
                    # 過去の製品一覧に載るものだけ販売終了と判定できる（載らない＝現行とは限らない）
                    "discontinued": "1" if p["phase"] == "rest" else "",
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
               "models": len({r["model_raw"] for r in rows}), "http": Counter(r["http_status"] for r in rows),
               "per_phase": Counter(p["phase"] for p in pages.values()), "anomalies": Counter(a["type"] for a in anomalies),
               **stats, "titles_top": Counter(r["title"] for r in rows).most_common(15)}
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

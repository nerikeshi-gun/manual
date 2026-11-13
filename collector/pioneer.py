"""パイオニア（carrozzeria: jpn.pioneer/ja/support/）の取説URL収集。

カテゴリ（main_cd）→ サブカテゴリの発売順一覧（s-year.php, 新しい順）→ 機種（s-information.php）
→ 取扱説明書ページ（s-manual.php, 同じクエリ）の順に辿る。発売順に新しいものから取る。

    python -m collector.pioneer listings
    python -m collector.pioneer fetch [--limit N]
    python -m collector.pioneer build
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

SUPPORT = "https://jpn.pioneer/ja/support/"
MAKER, DOMAIN, KEY = "パイオニア（carrozzeria）", "車載", "pioneer"
CAR_MAIN = {"001": "カーナビ", "003": "カーAV", "130": "車載用Wi-Fiルーター", "004": "スピーカー",
            "134": "ドライブレコーダー", "005": "システムアップ", "020": "カーナビバージョンアップ"}
MODELS, PAGES = RAW / f"{KEY}_models.jsonl", RAW / f"{KEY}_pages.jsonl"
_client: PoliteClient | None = None


def client() -> PoliteClient:
    global _client
    if _client is None:
        _client = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    return _client


def listings(_: argparse.Namespace) -> None:
    c = client()
    found: dict[str, dict] = {}
    order = 0
    for main_cd, main_label in CAR_MAIN.items():
        cat = BeautifulSoup(decode(c.get(f"{SUPPORT}category.php?main_cd={main_cd}")), "lxml")
        subs = {}
        for a in cat.find_all("a", href=True):
            q = parse_qs(urlsplit(a["href"]).query)
            if "s-year.php" in a["href"] and q.get("main_cd", [""])[0] == main_cd and q.get("sub_cd"):
                subs.setdefault(q["sub_cd"][0], a.get_text(" ", strip=True))
        for sub_cd, sub_label in subs.items():
            page = BeautifulSoup(decode(c.get(f"{SUPPORT}s-year.php?main_cd={main_cd}&sub_cd={sub_cd}")), "lxml")
            for a in page.find_all("a", href=True):
                if "s-information.php" not in a["href"]:
                    continue
                q = parse_qs(urlsplit(a["href"]).query)
                pno = q.get("product_no", [""])[0]
                if pno and pno not in found:
                    order += 1
                    found[pno] = {"product_no": pno, "model": q.get("bmp_type", [a.get_text(strip=True)])[0],
                                  "main_cd": main_cd, "sub_cd": sub_cd, "category": f"{main_label}／{sub_label}",
                                  "rank_in_list": order, "info_query": urlsplit(urljoin(SUPPORT, a["href"])).query}
            print(f"  {main_label}/{sub_label}: total {len(found)}", flush=True)
    write_jsonl(MODELS, found.values())
    print(f"models {len(found)}")


def fetch(args: argparse.Namespace) -> None:
    c = client()
    allm = load_jsonl(MODELS)
    done = {p["product_no"] for p in load_jsonl(PAGES) if p["status"] in (200, 404, "robots")}
    todo = [m for m in allm if m["product_no"] not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"models {len(allm)}, to fetch {len(todo)}", flush=True)
    lock = threading.Lock()

    def one(m):
        url = f"{SUPPORT}s-manual.php?{m['info_query']}"
        try:
            resp = c.get(url)
        except RobotsDisallowed:
            rec = {"product_no": m["product_no"], "status": "robots", "links": []}
        except requests.RequestException as exc:
            print(f"network error {m['model']}: {type(exc).__name__}", flush=True)
            time.sleep(15)
            return None
        else:
            if resp.status_code in (403, 429) or resp.status_code >= 500:
                time.sleep(60)
                return "blocked"
            soup = BeautifulSoup(decode(resp), "lxml")
            links = []
            for a in soup.find_all("a", href=True):
                href = urljoin(resp.url, a["href"].strip())
                parts = urlsplit(href)
                is_pdf = parts.path.lower().endswith(".pdf")
                is_viewer = parts.path.endswith("/manual_pdf.php") and "dl=1" not in parts.query  # プレビュー側のURLを採る
                if is_pdf or is_viewer:
                    row = a.find_parent("li", class_="list-box") or a.find_parent(["tr", "dd"])
                    row_text = row.get_text(" | ", strip=True) if row else ""
                    label = a.get_text(" ", strip=True)
                    if label in ("プレビュー", "ダウンロード", ""):
                        label = row_text.split(" | ")[0] if row_text else label
                    links.append({"href": href, "label": label, "row": row_text[:200]})
            rec = {"product_no": m["product_no"], "status": resp.status_code, "url": url, "links": links, "fetched_at": now()}
        with lock, PAGES.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return None

    run_parallel(todo, one)
    print("fetch complete", flush=True)


SIZE = re.compile(r"\s*[（(]\s*[\d.,]+\s*[KMG]?B\s*[）)]\s*$", re.I)


def build(_: argparse.Namespace) -> None:
    c = client()
    meta = {m["product_no"]: m for m in load_jsonl(MODELS)}
    pages = list({p["product_no"]: p for p in load_jsonl(PAGES)}.values())
    rows, anomalies, stats = [], [], Counter()
    for p in pages:
        m = meta.get(p["product_no"], {})
        if p["status"] != 200 or not p["links"]:
            anomalies.append({"type": "no_manual_links", "model": m.get("model", ""), "detail": p["status"], "url": p.get("url", "")})
            continue
        model = m.get("model", "").replace("_", " ")
        for l in {l["href"]: l for l in p["links"]}.values():
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": m.get("category", ""), "model_raw": model,
                "model_normalized": squash(model.split(" ")[0]), "title": SIZE.sub("", l["label"]) or l["row"][:60],
                "url": l["href"], "url_type": "pdf",  # manual_pdf.php はPDFを返すスクリプト
                "source_method": "crawl", "first_seen": "", "http_status": "",
                "checked_at": "", "model_unconfirmed": "0", "discontinued": "",
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
               "anomalies": Counter(a["type"] for a in anomalies), **stats,
               "titles_top": Counter(r["title"] for r in rows).most_common(15)}
    (RAW / f"{KEY}_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    sub.add_parser("listings").set_defaults(func=listings)
    f = sub.add_parser("fetch")
    f.add_argument("--limit", type=int, default=0)
    f.set_defaults(func=fetch)
    sub.add_parser("build").set_defaults(func=build)
    args = p.parse_args()
    NOTES.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()

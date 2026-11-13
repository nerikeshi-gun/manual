"""LIXIL（www.lixil.co.jp/support/manual/）のWeb取説（シリーズ単位）収集。

robots.txt の Sitemap にある web_manual_sitemap.xml（カテゴリ別）から各取説のトップ（/top?p_r_p_tag=）を読み、
タイトル（商品・シリーズ名）とURLを記録する。指示書「住設は品番のシリーズ単位でよい」に沿う。

品番単位の取説PDF（manualsearch?pid= → iinavi.inax.lixil.co.jp）は対象外:
- PDFのホスト iinavi.inax.lixil.co.jp は robots.txt で全面 Disallow。
- 品番ページは数十万件規模（1秒1回で約1週間）。

    python -m collector.lixil run
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import threading
import time
from collections import Counter

import requests
from bs4 import BeautifulSoup

from collector.common import (LOGS, NOTES, RAW, check_urls, decode, load_jsonl, now, run_parallel, write_anomalies,
                              write_rows)
from collector.polite import PoliteClient, RobotsDisallowed

SITE = "https://www.lixil.co.jp"
MAKER, DOMAIN, KEY = "LIXIL", "住設", "lixil"
PAGES = RAW / f"{KEY}_pages.jsonl"
CATS = {"building_apartment_store": "ビル・マンション・店舗", "door": "玄関ドア・引戸", "exterior": "エクステリア",
        "faucet": "水栓金具", "interior": "インテリア建材", "kitchen": "キッチン", "powderroom": "洗面化粧室",
        "smarthome": "スマートホーム", "toiletroom": "トイレ", "window_shutter": "窓・シャッター"}


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    index = [html.unescape(x) for x in re.findall(r"<loc>([^<]+)", c.get(f"{SITE}/support/manual/web_manual_sitemap.xml").text)]
    tops = []
    for sm in index:
        for loc in re.findall(r"<loc>([^<]+)", c.get(sm).text):
            loc = html.unescape(loc)
            m = re.match(rf"{re.escape(SITE)}/support/manual/([a-z_]+)/top\?p_r_p_tag=([\w\-]+)$", loc)
            if m:
                tops.append({"url": loc, "cat": m.group(1), "tag": m.group(2)})
    done = {p["url"] for p in load_jsonl(PAGES)}
    todo = [t for t in tops if t["url"] not in done]
    print(f"manual tops {len(tops)}, to fetch {len(todo)}", flush=True)
    lock = threading.Lock()

    def one(t):
        try:
            resp = c.get(t["url"])
        except (RobotsDisallowed, requests.RequestException) as exc:
            print(f"error {t['url']}: {type(exc).__name__}", flush=True)
            return None
        if resp.status_code in (403, 429) or resp.status_code >= 500:
            time.sleep(60)
            return "blocked"
        soup = BeautifulSoup(decode(resp), "lxml")
        title = soup.title.get_text(strip=True) if soup.title else ""
        parts = [p.strip() for p in title.split("|")]
        # 「LIXIL | お客さまサポート | <取説名> TOP | <商品名> | ...」
        manual = re.sub(r"\s*TOP$", "", parts[2]) if len(parts) > 2 else title
        product = parts[3] if len(parts) > 3 else ""
        rec = {**t, "status": resp.status_code, "title": title, "manual": manual, "product": product, "fetched_at": now()}
        with lock, PAGES.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return None

    run_parallel(todo, one)
    pages = list({p["url"]: p for p in load_jsonl(PAGES)}.values())
    rows, anomalies, stats = [], [], Counter()
    for p in pages:
        if p["status"] != 200:
            anomalies.append({"type": "page_not_200", "model": p["tag"], "detail": p["status"], "url": p["url"]})
            continue
        series = p["product"] or p["manual"]
        rows.append({
            "maker": MAKER, "domain": DOMAIN, "product_category": CATS.get(p["cat"], p["cat"]), "model_raw": series,
            "model_normalized": re.sub(r"\s+", "", series), "title": p["manual"], "url": p["url"], "url_type": "html",
            "source_method": "sitemap", "first_seen": "", "http_status": str(p["status"]), "checked_at": p["fetched_at"],
            "model_unconfirmed": "0" if series else "1", "discontinued": "",
        })
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"manual_tops": len(tops), "rows": len(rows), "series": len({r["model_raw"] for r in rows}),
               "per_category": Counter(r["product_category"] for r in rows), "anomalies": Counter(a["type"] for a in anomalies)}
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

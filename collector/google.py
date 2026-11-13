"""Google（Pixel）の取説相当ページの収集。

Google は機種別の取扱説明書PDFを出していない（使い方は Pixel ヘルプのWebページ）。
機種ごとに付属冊子に相当する「安全性と規制に関するガイド」がヘルプ記事として公開されているので、それを記録する。
入口: support.google.com/product-documentation/answer/9204905?hl=ja の
「安全と規制に関する情報」「アクセサリの安全と規制に関する情報」節のリンク（リンク文字列 = 機種名）。

    python -m collector.google run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.common import LOGS, NOTES, RAW, check_urls, decode, now, squash, write_jsonl, write_rows
from collector.polite import PoliteClient

PAGE = "https://support.google.com/product-documentation/answer/9204905?hl=ja"
MAKER, DOMAIN, KEY = "Google", "通信", "google"
SECTIONS = {"安全と規制に関する情報": "スマートフォン", "アクセサリの安全と規制に関する情報": "アクセサリ"}


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    resp = c.get(PAGE)
    soup = BeautifulSoup(decode(resp), "lxml")
    rows, items = [], []
    for h2 in soup.find_all("h2"):
        cat = SECTIONS.get(h2.get_text(" ", strip=True))
        if not cat:
            continue
        for el in h2.find_all_next():
            if el.name == "h2":
                break
            if el.name != "a" or not el.get("href"):
                continue
            url = urljoin(resp.url, el["href"]).split("#")[0]
            if "support.google.com" not in url or "/answer/" not in url or url.startswith(PAGE.split("?")[0]):
                continue
            label = el.get_text(" ", strip=True)
            items.append({"section": cat, "label": label, "url": url})
            names = [n.strip() for n in re.split(r"[、,]", label) if n.strip()]
            for n in names:
                rows.append({
                    "maker": MAKER, "domain": DOMAIN, "product_category": cat, "model_raw": n,
                    "model_normalized": squash(re.sub(r"[（(]\d{4}[)）]", "", re.sub(r"^Google\s+", "", n))), "title": f"安全性と規制に関するガイド（{label}）",
                    "url": url + "?hl=ja", "url_type": "html", "source_method": "crawl", "first_seen": "",
                    "http_status": "", "checked_at": "", "model_unconfirmed": "0", "discontinued": "",
                })
    rows = list({(r["url"], r["model_raw"]): r for r in rows}.values())
    # support.google.com は存在するページにも HEAD で 404 を返す（GET は 200）。HEAD が実質拒否されるので、
    # 指示書どおり Range 付き GET（先頭だけ・ストリームを即閉じる）で確認する。
    stats: Counter = Counter()
    statuses = {}
    for u in sorted({r["url"] for r in rows}):
        resp = c.get(u, headers={"Range": "bytes=0-0"}, stream=True)
        resp.close()
        statuses[u] = (str(resp.status_code), now())
        stats[f"range_get_{resp.status_code}"] += 1
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    write_jsonl(RAW / f"{KEY}_pages.jsonl", [{"url": PAGE, "status": resp.status_code, "items": items, "fetched_at": now()}])
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    summary = {"rows": len(rows), "unique_urls": len({r["url"] for r in rows}), "models": len({r["model_raw"] for r in rows}),
               "http": Counter(r["http_status"] for r in rows), "per_category": Counter(r["product_category"] for r in rows), **stats}
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

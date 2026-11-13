"""クリナップ（cleanup.jp/support/manual/ 商品取扱説明書検索）の取説URL収集。

検索フォームは POST（sel01=種類 0:取扱説明書, sel02=商品カテゴリー, sel03=シリーズ 0:すべて, sel04/sel05=0, page=n）。
結果は ol.results の行（シリーズ・区分・品番・名称・発行年月・PDFリンク）、1ページ50件。
発行年月が「YYYY.MM - 現行」の行を現行品、「YYYY.MM - YYYY.MM」を販売終了品として扱う。
サイト注記: 2016年2月現行品以降が対象、一部検索に含まれない取説あり。

    python -m collector.cleanup run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.common import LOGS, NOTES, RAW, check_urls, decode, now, squash, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

PAGE = "https://cleanup.jp/support/manual/"
MAKER, DOMAIN, KEY = "クリナップ", "住設", "cleanup"


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    soup = BeautifulSoup(decode(c.get(PAGE)), "lxml")
    cats = [(o["value"], o.get_text(strip=True)) for o in soup.select("select#sel02 option")]
    pages, items = [], []
    for value, label in cats:
        page = 1
        while True:
            resp = c.post(PAGE, data={"sel01": "0", "sel02": value, "sel03": "0", "sel04": "0", "sel05": "0",
                                      "keywords": "", "page": str(page)})
            s = BeautifulSoup(decode(resp), "lxml")
            got = 0
            for ol in s.select("ol.results"):
                if "title" in (ol.get("class") or []):
                    continue
                cell = {li.get("class")[0]: li for li in ol.find_all("li") if li.get("class")}
                a = cell.get("list8") and cell["list8"].find("a", href=True)
                if not a:
                    continue
                got += 1
                items.append({"category": label, "series": cell["list3"].get_text(strip=True),
                              "kubun": cell["list4"].get_text(strip=True), "hinban": cell["list5"].get_text(strip=True),
                              "name": cell["list6"].get_text(strip=True), "period": cell["list7"].get_text(" ", strip=True),
                              "url": urljoin(resp.url, a["href"])})
            m = re.search(r"(\d+)\s*/\s*(\d+)", (s.select_one(".page") or s).get_text(" ", strip=True)) if s.select_one(".page") else None
            total = int(m.group(2)) if m else 1
            pages.append({"category": label, "page": page, "status": resp.status_code, "rows": got, "fetched_at": now()})
            print(f"  {label} p{page}/{total}: {got}", flush=True)
            if page >= total or not got:
                break
            page += 1
    rows = []
    for it in items:
        model = it["hinban"] or it["name"]
        current = bool(re.search(r"現行\s*$", it["period"]))
        title = "取扱説明書（" + "・".join(x for x in (it["series"], it["kubun"], it["name"]) if x) + f"／{it['period']}）"
        rows.append({
            "maker": MAKER, "domain": DOMAIN, "product_category": it["category"], "model_raw": model,
            "model_normalized": squash(model), "title": title, "url": it["url"], "url_type": "pdf",
            "source_method": "search_form", "first_seen": "", "http_status": "", "checked_at": "",
            "model_unconfirmed": "0" if model else "1", "discontinued": "0" if current else "1",
        })
    stats: Counter = Counter()
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    url_models = defaultdict(set)
    for r in rows:
        url_models[r["url"]].add(r["model_raw"])
    anomalies = [{"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": u}
                 for u, ms in url_models.items() if len(ms) > 1]
    anomalies += [{"type": "no_hinban", "model": r["model_raw"], "detail": "品番欄が空、名称を型番欄に使用", "url": r["url"]}
                  for r, it in zip(rows, items) if not it["hinban"]]
    write_jsonl(RAW / f"{KEY}_pages.jsonl", [{"pages": pages, "items": items}])
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"rows": len(rows), "unique_urls": len(url_models), "models": len({r["model_raw"] for r in rows}),
               "current_rows": sum(r["discontinued"] == "0" for r in rows), "http": Counter(r["http_status"] for r in rows),
               "per_category": Counter(r["product_category"] for r in rows), "anomalies": Counter(a["type"] for a in anomalies), **stats}
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

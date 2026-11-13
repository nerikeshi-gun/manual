"""トヨタ（manual.toyota.jp）の車両取扱説明書URL収集。

車種一覧 manual.toyota.jp/index.html → 車種ページ manual.toyota.jp/<車種>/ 。
車種ページは世代（dl.block, dt h4 = 生産年月の範囲）ごとに、資料（div.manual, h5 = 資料名（グレード/動力））と
生産年月ごとのリンク（p = 「生産年月：…」, a = HTML/PDF）が並ぶ。
指示書の「車両は型番の代わりに 車種/年式/グレード」に沿い、model_raw を「車種／生産年月／グレード」とする。
生産年月が「…～」（終わりが無い）ものを現行（discontinued=0）、終わりがあるものを 1 とする。

    python -m collector.toyota run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.common import LOGS, NOTES, RAW, check_urls, decode, now, name_key, squash, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

SITE = "https://manual.toyota.jp/"
MAKER, DOMAIN, KEY = "トヨタ", "車載", "toyota"


def parse_car(html: str, base: str) -> tuple[str, list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    h3 = soup.find("h3")
    car = h3.get_text(" ", strip=True) if h3 else ""
    out = []
    for block in soup.select("dl.block"):
        gen = block.select_one("dt h4")
        generation = gen.get_text(" ", strip=True) if gen else ""
        for man in block.select("div.manual"):
            h5 = man.find("h5")
            doc = re.sub(r"\s+", "", h5.get_text("", strip=True)) if h5 else ""
            grade = (re.search(r"[（(]([^（）()]+)[)）]\s*$", doc) or [None, ""])[1]
            period = ""
            for el in man.find_all(["p", "a"]):
                if el.name == "p":
                    period = re.sub(r"^生産年月[：:]\s*", "", el.get_text(" ", strip=True))
                elif el.get("href"):
                    out.append({"car": car, "generation": generation, "doc": doc, "grade": grade, "period": period or generation,
                                "kind": el.get_text(strip=True), "url": urljoin(base, el["href"])})
    return car, out


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    idx = decode(c.get(SITE + "index.html"))
    slugs = sorted(set(re.findall(r'href="(?:https://manual\.toyota\.jp)?/?([a-z0-9_\-]+)/"', idx)) - {"pages", "pdf", "toyota"})
    pages, items = [], []
    for slug in slugs:
        resp = c.get(f"{SITE}{slug}/")
        car, got = parse_car(decode(resp), resp.url)
        for g in got:
            g["slug"] = slug
        items += got
        pages.append({"slug": slug, "car": car, "status": resp.status_code, "links": len(got), "fetched_at": now()})
        print(f"  {slug} {car}: {len(got)}", flush=True)
    rows = []
    for it in items:
        model = "／".join(x for x in (it["car"], it["period"], it["grade"]) if x)
        rows.append({
            "maker": MAKER, "domain": DOMAIN, "product_category": "自動車", "model_raw": model,
            "model_normalized": name_key(it["car"]), "title": it["doc"], "url": it["url"],
            "url_type": "pdf" if it["url"].lower().endswith(".pdf") else "html", "source_method": "crawl",
            "first_seen": "", "http_status": "", "checked_at": "", "model_unconfirmed": "0" if it["car"] else "1",
            "discontinued": "0" if re.search(r"～\s*$", it["generation"]) else "1",
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
    anomalies += [{"type": "no_links", "model": p["car"] or p["slug"], "detail": p["status"], "url": f"{SITE}{p['slug']}/"}
                  for p in pages if not p["links"]]
    write_jsonl(RAW / f"{KEY}_pages.jsonl", [{"pages": pages, "items": items}])
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"cars": len(pages), "rows": len(rows), "unique_urls": len(url_models),
               "current_rows": sum(r["discontinued"] == "0" for r in rows), "http": Counter(r["http_status"] for r in rows),
               "per_doc": Counter(r["title"] for r in rows).most_common(15), "anomalies": Counter(a["type"] for a in anomalies), **stats}
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

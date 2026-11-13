"""レクサス（manual.lexus.jp）の車両取扱説明書URL収集。

車種一覧 manual.lexus.jp/ → 車種ページ manual.lexus.jp/<車種>/ 。
車種ページは div.mp-group（data-category = ガソリン/ハイブリッド等）ごとに、世代の .mp-unit（mp-unit_date = 生産年月、
mp-unit_model = モデル名）と、資料の .mp-unit（mp-unit_title）> li（mp-unit_listDate = 生産年月, a = HTML/PDF）が並ぶ。
model_raw は「モデル名／生産年月／動力（グレード相当）」。世代の生産年月が「…～」なら現行（discontinued=0）。

    python -m collector.lexus run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.common import LOGS, NOTES, RAW, check_urls, decode, name_key, now, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

SITE = "https://manual.lexus.jp/"
MAKER, DOMAIN, KEY = "レクサス", "車載", "lexus"


def parse(html: str, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for group in soup.select("div.mp-group"):
        power = group.get("data-category", "")
        gen_date = group.select_one(".mp-unit_date")
        gen_model = group.select_one(".mp-unit_model")
        generation = gen_date.get_text(" ", strip=True) if gen_date else ""
        model = gen_model.get_text(" ", strip=True) if gen_model else ""
        for unit in group.select(".mp-unit"):
            t = unit.select_one(".mp-unit_title")
            if not t:
                continue
            doc = t.get_text(" ", strip=True)
            for li in unit.select("li"):
                d = li.select_one(".mp-unit_listDate")
                period = re.sub(r"^生産年月[：:]\s*", "", d.get_text(" ", strip=True)) if d else generation
                for a in li.find_all("a", href=True):
                    out.append({"model": model, "generation": generation, "power": power, "doc": doc,
                                "period": period, "kind": a.get_text(strip=True), "url": urljoin(base, a["href"])})
    return out


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    idx = decode(c.get(SITE))
    slugs = sorted(set(re.findall(r'href="(?:https://manual\.lexus\.jp)?/?([a-z0-9_\-]+)/"', idx)))
    items, pages = [], []
    for slug in slugs:
        resp = c.get(f"{SITE}{slug}/")
        got = parse(decode(resp), resp.url)
        for g in got:
            g["slug"] = slug
        items += got
        pages.append({"slug": slug, "status": resp.status_code, "links": len(got), "fetched_at": now()})
        print(f"  {slug}: {len(got)}", flush=True)
    rows = []
    for it in items:
        name = it["model"] or it["slug"].upper()
        rows.append({
            "maker": MAKER, "domain": DOMAIN, "product_category": "自動車",
            "model_raw": "／".join(x for x in (name, it["period"], it["power"]) if x), "model_normalized": name_key(name),
            "title": it["doc"], "url": it["url"], "url_type": "pdf" if it["url"].lower().endswith(".pdf") else "html",
            "source_method": "crawl", "first_seen": "", "http_status": "", "checked_at": "",
            "model_unconfirmed": "0" if it["model"] else "1",
            "discontinued": "0" if re.search(r"～\s*$", it["generation"]) else "1",
        })
    rows = list({(r["url"], r["model_raw"], r["title"]): r for r in rows}.values())
    stats: Counter = Counter()
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    url_models = defaultdict(set)
    for r in rows:
        url_models[r["url"]].add(r["model_raw"])
    anomalies = [{"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": u}
                 for u, ms in url_models.items() if len(ms) > 1]
    anomalies += [{"type": "no_links", "model": p["slug"], "detail": p["status"], "url": f"{SITE}{p['slug']}/"} for p in pages if not p["links"]]
    write_jsonl(RAW / f"{KEY}_pages.jsonl", [{"pages": pages, "items": items}])
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"cars": len(pages), "rows": len(rows), "unique_urls": len(url_models),
               "current_rows": sum(r["discontinued"] == "0" for r in rows), "http": Counter(r["http_status"] for r in rows),
               "per_doc": Counter(r["title"] for r in rows).most_common(10), "anomalies": Counter(a["type"] for a in anomalies), **stats}
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

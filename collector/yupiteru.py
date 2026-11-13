"""ユピテル（製品データベース www2.yupiteru.co.jp/manual/ → api.yupiteru.co.jp）の取説URL収集。

製品データベースは Vue アプリで、公開APIを呼んでいる（認証なし、robots.txt は制限なし）。
- 一覧: api/product_database/products?productReCategoryId=<id>&page=<n>（既定で販売終了品を除く。addEndSale=true で含む）
- 詳細: api/product_database/products/<id> の productDetails に取説PDFのリンク

    python -m collector.yupiteru run --phase current|all
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict

from collector.common import LOGS, NOTES, RAW, check_urls, load_jsonl, now, squash, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

API = "https://api.yupiteru.co.jp/api/product_database/"
MAKER, DOMAIN, KEY = "ユピテル", "車載", "yupiteru"
PAGES = RAW / f"{KEY}_pages.jsonl"
DOC = re.compile(r"説明書|マニュアル|ガイド")


def run(args: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    cats = c.get(API + "product_re_categories").json()["response"]["productReCategories"]
    listed: dict[int, dict] = {}
    for parent in cats:
        for child in parent.get("children", []):
            page = 1
            while True:
                q = f"products?productReCategoryId={child['id']}&page={page}" + ("&addEndSale=true" if args.phase == "all" else "")
                resp = c.get(API + q).json().get("response", {})
                items = resp.get("products") or []
                for p in items:
                    listed.setdefault(p["id"], {**p, "parent": parent["name"], "child": child["name"],
                                                "current": args.phase == "current"})
                total = resp.get("allProductsCount") or 0
                if not items or page * 25 >= total:
                    break
                page += 1
            print(f"  {parent['name']}/{child['name']}: total {len(listed)}", flush=True)
    done = {p["id"] for p in load_jsonl(PAGES)}
    with PAGES.open("a", encoding="utf-8") as out:
        for pid, p in listed.items():
            if pid in done:
                continue
            detail = c.get(f"{API}products/{pid}").json().get("response", {}).get("product", {})
            out.write(json.dumps({"id": pid, "name": p["name"], "release": f"{p.get('releaseYear') or ''}-{p.get('releaseMonth') or ''}",
                                  "category": f"{p['parent']}／{p['child']}", "current": p["current"],
                                  "details": detail.get("productDetails", []), "fetched_at": now()}, ensure_ascii=False) + "\n")
            out.flush()
    build(c)


def build(c: PoliteClient) -> None:
    pages = list({p["id"]: p for p in load_jsonl(PAGES)}.values())
    rows, anomalies, stats = [], [], Counter()
    for p in pages:
        docs = [d for d in p["details"] if DOC.search(d.get("title", "")) and d.get("linkUrl")]
        if not docs:
            anomalies.append({"type": "no_manual_links", "model": p["name"], "detail": p["release"], "url": ""})
            continue
        for d in {d["linkUrl"]: d for d in docs}.values():
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": p["category"], "model_raw": p["name"],
                "model_normalized": squash(p["name"]), "title": d["title"], "url": d["linkUrl"],
                "url_type": "pdf" if d["linkUrl"].lower().endswith(".pdf") else "html", "source_method": "api",
                "first_seen": "", "http_status": "", "checked_at": "", "model_unconfirmed": "0",
                "discontinued": "0" if p["current"] else "",
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
    summary = {"products": len(pages), "rows": len(rows), "unique_urls": len(url_models),
               "models_with_manual": len({r["model_raw"] for r in rows}), "http": Counter(r["http_status"] for r in rows),
               "anomalies": Counter(a["type"] for a in anomalies), **stats}
    (RAW / f"{KEY}_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    r = p.add_subparsers(required=True).add_parser("run")
    r.add_argument("--phase", choices=["current", "all"], default="current")
    r.set_defaults(func=run)
    args = p.parse_args()
    NOTES.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()

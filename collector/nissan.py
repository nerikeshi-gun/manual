"""日産（www.nissan.co.jp/OPTIONAL-PARTS/NAVIOM/ 取扱説明書／点検整備方式）の車両取扱説明書URL収集。

ページはJS（JS/index2016.js）が index.xml（モデル一覧と年式）と XML/<モデルID>.xml（年式ごとの資料）を読んで表示する。
XML/<id>.xml: model > nenshiki(value=年式) > 資料区分 > [category(name)] > pdf(path, device) 。path はサイトルート相対。
資料区分のうち取説にあたるものを採る:
  op-inst=取扱説明書（デジタル） / guid=簡単早わかりガイド / tori=車両取扱説明書 /
  navi-maker=ナビゲーションシステム（標準・メーカーOP） / accessory=アクセサリー / navi-dealer=ナビ（ディーラーOP）
除外: movie（動画）, software（ソフトウェア更新）, im-sys（点検整備方式）。device は ALL と PC のみ（SP は同内容のスマホ版）。
model_raw は「モデル名／年式／資料の適用期間など」（指示書の車種/年式/グレード）。

    python -m collector.nissan run
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.common import LOGS, NOTES, RAW, check_urls, decode, name_key, now, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

BASE = "https://www.nissan.co.jp/OPTIONAL-PARTS/NAVIOM/"
MAKER, DOMAIN, KEY = "日産", "車載", "nissan"
SECTIONS = {"op-inst": "取扱説明書", "guid": "簡単早わかりガイド", "tori": "車両取扱説明書",
            "navi-maker": "ナビゲーションシステム（標準、メーカーオプション）", "accessory": "アクセサリー",
            "navi-dealer": "ナビゲーションシステム（ディーラーオプション）"}


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    c.get(BASE)  # ご利用条件（同意は画面上の文言。ユーザーの包括承認あり）
    index = BeautifulSoup(decode(c.get(BASE + "index.xml")), "xml")
    models = [(m["id"], m.get("name", m["id"]), [n["value"] for n in m.find_all("nenshiki")]) for m in index.find_all("model")]
    rows, pages, skipped = [], [], Counter()
    for mid, name, years in models:
        resp = c.get(f"{BASE}XML/{mid}.xml")
        x = BeautifulSoup(decode(resp), "xml")
        got = 0
        for nen in x.find_all("nenshiki"):
            year = nen.get("value", "")
            for sec in nen.find_all(recursive=False):
                label = SECTIONS.get(sec.name)
                if not label:
                    skipped[sec.name] += 1
                    continue
                for pdf in sec.find_all("pdf"):
                    if pdf.get("device", "ALL") not in ("ALL", "PC") or not pdf.get("path"):
                        continue
                    cat = pdf.find_parent("category")
                    text = pdf.get_text(" ", strip=True)
                    url = urljoin(BASE, pdf["path"])
                    title = label + (f"／{cat['name']}" if cat and cat.get("name") else "") + (f"／{text}" if text else "")
                    rows.append({
                        "maker": MAKER, "domain": DOMAIN, "product_category": "自動車", "model_raw": f"{name}／{year}年式",
                        "model_normalized": name_key(name), "title": title, "url": url,
                        "url_type": "pdf" if url.lower().endswith(".pdf") else "html", "source_method": "static_xml",
                        "first_seen": "", "http_status": "", "checked_at": "", "model_unconfirmed": "0", "discontinued": "",
                    })
                    got += 1
        pages.append({"model_id": mid, "name": name, "years": years, "status": resp.status_code, "links": got, "fetched_at": now()})
        print(f"  {mid} {name}: {got}", flush=True)
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
    anomalies += [{"type": "no_links", "model": p["name"], "detail": p["status"], "url": f"{BASE}XML/{p['model_id']}.xml"}
                  for p in pages if not p["links"]]
    write_jsonl(RAW / f"{KEY}_pages.jsonl", pages)
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"models": len(models), "rows": len(rows), "unique_urls": len(url_models),
               "model_years": len({r["model_raw"] for r in rows}), "http": Counter(r["http_status"] for r in rows),
               "per_section": Counter(r["title"].split("／")[0] for r in rows), "skipped_sections": skipped,
               "per_type": Counter(r["url_type"] for r in rows), "anomalies": Counter(a["type"] for a in anomalies), **stats}
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

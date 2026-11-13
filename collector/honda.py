"""ホンダ（四輪: www.honda.co.jp/ownersmanual/HondaMotor/auto/）の車両取扱説明書URL収集。

取扱説明書閲覧サービスはページ内JS（js/search.js）が data/search.json を読んで表示している（認証なし）。
search.json: CarModelData（車種）→ ModelYears（年式, ReleaseDate=発売年月）→ Docs（資料, DocCategoryId で資料名）。
URLの組み立ては search.js と同じ:
- PDF: <auto>/../../pdf/auto/<FolderName>/<PDFFileName>?<PDFParameter>（= /ownersmanual/pdf/auto/...）
- HTML（Web取説）: doc.WebOMFileName（そのまま）
- LINK: doc.LinkURL
指示書の「車両は型番の代わりに 車種/年式/グレード」に沿い、model_raw を「車種／年式（発売年月）」とする。

    python -m collector.honda run
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from urllib.parse import urljoin

from collector.common import LOGS, NOTES, RAW, check_urls, now, name_key, squash, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

BASE = "https://www.honda.co.jp/ownersmanual/HondaMotor/auto/"
PDF_BASE = urljoin(BASE, "../../pdf/auto") + "/"
MAKER, DOMAIN, KEY = "ホンダ", "車載", "honda"


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    data = c.get(BASE + "data/search.json").json()
    cats = {x["Id"]: x for x in data["DocCategoryMaster"]}
    carcats = {x["Id"]: x["Name"] for x in data["CarCategoryMaster"]}
    rows, anomalies = [], []
    for car in data["CarModelData"]:
        for my in car.get("ModelYears", []):
            rel = my.get("ReleaseDate") or ""
            when = f"{my.get('Year')}年式" + (f"（{rel[:4]}年{rel[4:6]}月発売）" if len(rel) >= 6 else "")
            model = f"{car['Name']}／{when}"
            for doc in my.get("Docs", []):
                cat = cats.get(doc.get("DocCategoryId"), {})
                title = cat.get("Name", "") + (f"（{doc['Content']}）" if doc.get("Content") else "")
                links = []
                if cat.get("IsViewWebOM") and doc.get("WebOMFileName"):
                    links.append((urljoin(BASE, doc["WebOMFileName"]), "html"))
                if cat.get("IsViewPDF") and doc.get("PDFFileName"):
                    q = f"?{doc['PDFParameter']}" if doc.get("PDFParameter") else ""
                    links.append((f"{PDF_BASE}{car['FolderName']}/{doc['PDFFileName']}{q}", "pdf"))
                if cat.get("IsViewLink") and doc.get("LinkURL"):
                    links.append((doc["LinkURL"], "html"))
                if not links:
                    anomalies.append({"type": "doc_without_link", "model": model, "detail": title, "url": ""})
                for url, kind in links:
                    rows.append({
                        "maker": MAKER, "domain": DOMAIN, "product_category": carcats.get(car.get("CarCategoryId"), "自動車"),
                        "model_raw": model, "model_normalized": name_key(car["Name"]), "title": title, "url": url,
                        "url_type": kind, "source_method": "static_json", "first_seen": "", "http_status": "",
                        "checked_at": "", "model_unconfirmed": "0", "discontinued": "",
                    })
    stats: Counter = Counter()
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    url_models = defaultdict(set)
    for r in rows:
        url_models[r["url"]].add(r["model_raw"])
    anomalies += [{"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": u}
                  for u, ms in url_models.items() if len(ms) > 1]
    write_jsonl(RAW / f"{KEY}_pages.jsonl", [{"url": BASE + "data/search.json", "cars": len(data["CarModelData"]), "fetched_at": now()}])
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"cars": len(data["CarModelData"]), "rows": len(rows), "unique_urls": len(url_models),
               "models": len({r["model_raw"] for r in rows}), "http": Counter(r["http_status"] for r in rows),
               "per_title": Counter(r["title"] for r in rows).most_common(15), "per_type": Counter(r["url_type"] for r in rows),
               "anomalies": Counter(a["type"] for a in anomalies), **stats}
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

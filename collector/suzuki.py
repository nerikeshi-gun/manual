"""スズキ（四輪: www.suzuki.co.jp/car/owners_manual/）の車両取扱説明書URL収集。

オーナーズマニュアルのページはJS（assets/js/common.js）が data/data.csv を読み、detail.js がリンクを組み立てる。
CSV列: 0 MAN_ID, 1 MAN_NO, 2 MAN_DT(適用年月 YYYYMM), 3 MAN_RF(抜粋版PDF名), 4 MAN_FL(PDF名), 5 MAN_HT(HTMLフォルダ),
 10 PRO_TP(Y=四輪), 11 CAR_SZ(1 軽/2 普通), 15 CAR_NM(車名), 16 MDL_CD(機種記号)
リンク（detail.js と同じ組み立て）:
- デジタル取扱説明書 HTML: /car/owners_manual/data/html/<MAN_HT>/ja/html/home.html?item=top.html
- 取扱説明書（抜粋版）PDF: ./data/pdf/<MAN_RF>.pdf
- 取扱説明書 PDF: ./data/pdf/<MAN_FL>.pdf
閲覧時はご利用条件（terms.html）への同意をブラウザの sessionStorage に記録するだけで、リンク自体は同意なしで開ける。
model_raw は「車名／機種記号／適用年月～」（指示書の車種/年式/グレード）。

    python -m collector.suzuki run
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter, defaultdict

from collector.common import LOGS, NOTES, RAW, check_urls, now, name_key, squash, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

BASE = "https://www.suzuki.co.jp/car/owners_manual/"
MAKER, DOMAIN, KEY = "スズキ", "車載", "suzuki"
SIZES = {"1": "軽自動車", "2": "普通乗用車"}


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    c.get(BASE + "terms.html")  # ご利用条件（ユーザーの包括承認あり）
    resp = c.get(BASE + "data/data.csv?1")
    text = resp.content.decode("utf-8-sig")
    recs = [r + [""] * (18 - len(r)) for r in csv.reader(io.StringIO(text)) if r and r[0].strip()]
    rows = []
    for r in recs:
        man_dt, man_rf, man_fl, man_ht = r[2].strip(), r[3].strip(), r[4].strip(), r[5].strip()
        if r[10].strip() != "Y":
            continue
        when = f"{man_dt[:4]}年{int(man_dt[4:6])}月～" if len(man_dt) >= 6 and man_dt[4:6].isdigit() else man_dt
        model = "／".join(x for x in (r[15].strip(), r[16].strip(), when) if x)
        links = []
        if man_ht:
            links.append((f"{BASE}data/html/{man_ht}/ja/html/home.html?item=top.html", "デジタル取扱説明書", "html"))
        if man_rf:
            links.append((f"{BASE}data/pdf/{man_rf}.pdf", "取扱説明書（抜粋版）", "pdf"))
        if man_fl:
            links.append((f"{BASE}data/pdf/{man_fl}.pdf", "取扱説明書", "pdf"))
        for url, title, kind in links:
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": SIZES.get(r[11].strip(), "自動車"),
                "model_raw": model, "model_normalized": name_key(r[15].strip()), "title": f"{title}（{r[1].strip()}）",
                "url": url, "url_type": kind, "source_method": "static_csv", "first_seen": "", "http_status": "",
                "checked_at": "", "model_unconfirmed": "0" if r[15].strip() else "1", "discontinued": "",
            })
    rows = list({(r["url"], r["model_raw"]): r for r in rows}.values())
    stats: Counter = Counter()
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    url_models = defaultdict(set)
    for r in rows:
        url_models[r["url"]].add(r["model_raw"])
    anomalies = [{"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": u}
                 for u, ms in url_models.items() if len(ms) > 1]
    write_jsonl(RAW / f"{KEY}_pages.jsonl", [{"url": BASE + "data/data.csv", "status": resp.status_code, "records": len(recs), "fetched_at": now()}])
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"csv_records": len(recs), "rows": len(rows), "unique_urls": len(url_models),
               "cars": len({r["model_normalized"] for r in rows}), "http": Counter(r["http_status"] for r in rows),
               "per_type": Counter(r["url_type"] for r in rows), "shared_url": len(anomalies), **stats}
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

"""三菱自動車（www.mitsubishi-motors.co.jp/afterservice/manual/）の車両取扱説明書URL収集。

取扱説明書一覧ページ1枚に車種カード（li[data-carmodel]）があり、
「標準・メーカーオプション」「アクセサリー」（h3）ごとに PDF／HTML の取説リンクが並ぶ。
取扱説明動画・地図更新手順などのリンクは取説ではないので除く。
model_raw は「車種／版（YYYY年M月版）」（指示書の車種/年式/グレード。グレード相当の「PHEVモデル」等は title に残す）。

    python -m collector.mitsubishi_motors run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from collector.common import LOGS, NOTES, RAW, check_urls, decode, now, name_key, squash, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

PAGE = "https://www.mitsubishi-motors.co.jp/afterservice/manual/index.html"
MAKER, DOMAIN, KEY = "三菱自動車", "車載", "mitsubishi_motors"
SIZE = re.compile(r"\s*\[(?:PDF|html)[^\]]*\]|\s*（別ウィンドウで開く）", re.I)


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    resp = c.get(PAGE)
    soup = BeautifulSoup(decode(resp), "lxml")
    rows, items = [], []
    for card in soup.select("li[data-carmodel]"):
        name_a = card.select_one(".manualCard__link a")
        car = name_a.get_text(" ", strip=True) if name_a else card["data-carmodel"]
        for opt in card.select(".manualCard__option"):
            h3 = opt.find("h3")
            section = h3.get_text(" ", strip=True) if h3 else ""
            for a in opt.find_all("a", href=True):
                url = urljoin(resp.url, a["href"])
                path = urlsplit(url).path
                if "/afterservice/manual/" not in path or "movie_guide" in path:
                    continue
                if not (path.lower().endswith(".pdf") or "/manual/html/" in path):
                    continue
                label = SIZE.sub("", a.get_text(" ", strip=True)).strip()
                ver = re.search(r"(\d{4})年(\d{1,2})月版", label)
                model = car + (f"／{ver.group(1)}年{ver.group(2)}月版" if ver else "")
                items.append({"car": car, "section": section, "label": label, "url": url})
                rows.append({
                    "maker": MAKER, "domain": DOMAIN, "product_category": f"自動車／{section}" if section else "自動車",
                    "model_raw": model, "model_normalized": name_key(car), "title": label,
                    "url": url, "url_type": "pdf" if path.lower().endswith(".pdf") else "html", "source_method": "crawl",
                    "first_seen": "", "http_status": "", "checked_at": "", "model_unconfirmed": "0", "discontinued": "",
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
    write_jsonl(RAW / f"{KEY}_pages.jsonl", [{"url": PAGE, "status": resp.status_code, "items": items, "fetched_at": now()}])
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"rows": len(rows), "unique_urls": len(url_models), "cars": len({r["model_normalized"] for r in rows}),
               "http": Counter(r["http_status"] for r in rows), "per_type": Counter(r["url_type"] for r in rows),
               "shared_url": len(anomalies), **stats}
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

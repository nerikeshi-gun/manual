"""コムテック（www.e-comtec.co.jp/0_etc/manual/）の取説URL収集。

取扱説明書ページ1枚に、製品カテゴリごとのプルダウン（option の value が PDF のパス、表示が型番）が並んでいる。
現行／生産終了の区別は無い。

    python -m collector.comtec run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from collector.common import LOGS, NOTES, RAW, check_urls, decode, now, squash, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

PAGE = "https://www.e-comtec.co.jp/0_etc/manual/"
MAKER, DOMAIN, KEY = "コムテック", "車載", "comtec"
SUFFIX = re.compile(r"\s*[（(][^（）()]*(?:版|[KMG]B?|M)[^（）()]*[）)]\s*$")


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    resp = c.get(PAGE)
    soup = BeautifulSoup(decode(resp), "lxml")
    items, rows, anomalies = [], [], []
    for sel in soup.find_all("select"):
        heading = sel.find_previous(["h2", "h3", "h4", "h5"])
        category = heading.get_text(" ", strip=True) if heading else ""
        for opt in sel.find_all("option"):
            value = (opt.get("value") or "").strip()
            if not value:
                continue
            url = urljoin(resp.url, value)
            label = unicodedata.normalize("NFKC", opt.get_text(" ", strip=True))
            edition = re.search(r"[（(]([^（）()]*版)", label)
            text = SUFFIX.sub("", label).strip()
            model, _, desc = text.partition("_") if "_" in text else (text.split(" ")[0] if re.match(r"^[A-Z]", text) and "　" not in text and len(text.split(" ")) > 1 and not re.match(r"^(ZERO|RADARPHONE|MOTO)", text) else text, "", "")
            items.append({"category": category, "label": label, "url": url})
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": category, "model_raw": model.strip(),
                "model_normalized": squash(model), "title": ("取扱説明書" + (f"（{edition.group(1)}）" if edition else "")),
                "url": url, "url_type": "pdf" if urlsplit(url).path.lower().endswith(".pdf") else "html",
                "source_method": "crawl", "first_seen": "", "http_status": "", "checked_at": "",
                "model_unconfirmed": "0", "discontinued": "",
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
    write_jsonl(RAW / f"{KEY}_pages.jsonl", [{"url": PAGE, "status": resp.status_code, "items": items, "fetched_at": now()}])
    write_rows(RAW / f"{KEY}_manuals.csv", rows)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"rows": len(rows), "unique_urls": len(url_models), "models": len({r["model_raw"] for r in rows}),
               "http": Counter(r["http_status"] for r in rows), "shared_url": sum(len(m) > 1 for m in url_models.values()), **stats}
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

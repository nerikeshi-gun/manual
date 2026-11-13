"""東芝ライフスタイル（www.toshiba-living.jp）の取説URL収集。

    python -m collector.toshiba models      # カテゴリ一覧から全型番（発売年月つき）
    python -m collector.toshiba fetch --since 2024-01   # 指定年月以降の発売分（新しい順）
    python -m collector.toshiba fetch                   # 残り全部
    python -m collector.toshiba build

取説一覧は「ご利用の条件」への同意（rev.php に YN=Y をPOST）の後に表示される。
規約への同意はユーザーの承認済み（2026-11-13、今後の同種の規約も含む）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from collector.common import (LOGS, NOTES, RAW, check_urls, decode, load_jsonl, now, run_parallel, squash,
                              write_anomalies, write_jsonl, write_rows)
from collector.polite import PoliteClient, RobotsDisallowed

SITE = "https://www.toshiba-living.jp"
MAKER, DOMAIN, KEY = "東芝ライフスタイル", "家電", "toshiba"
MODELS, PAGES = RAW / f"{KEY}_models.jsonl", RAW / f"{KEY}_pages.jsonl"
ROWS, ANOMALIES = RAW / f"{KEY}_manuals.csv", RAW / f"{KEY}_anomalies.csv"
RELEASE = re.compile(r"(\d{4})年\s*(\d{1,2})月")
_client: PoliteClient | None = None


def client() -> PoliteClient:
    global _client
    if _client is None:
        _client = PoliteClient(log_path=LOGS / f"{KEY}_requests.log", session_per_thread=True)
    return _client


def soup_of(url: str) -> BeautifulSoup:
    return BeautifulSoup(decode(client().get(url)), "lxml")


def models(_: argparse.Namespace) -> None:
    top = soup_of(f"{SITE}/search.php")
    sc1 = sorted({re.search(r"sc1=(\d+)", a["href"]).group(1) for a in top.find_all("a", href=True)
                  if re.search(r"search_category_list\.php\?sc1=\d+", a["href"])})
    sc2: dict[str, str] = {}
    for s1 in sc1:
        page = soup_of(f"{SITE}/search_category_list.php?sc1={s1}")
        crumb = page.title.get_text(strip=True) if page.title else ""
        for a in page.find_all("a", href=True):
            m = re.match(r"^search_category_list\.php\?sc2=(\d+)$", a["href"])
            if m:
                sc2.setdefault(m.group(1), a.get_text(" ", strip=True))
    print(f"sc1 {len(sc1)}, sc2 {len(sc2)}", flush=True)
    out: dict[str, dict] = {}
    for s2, label in sc2.items():
        offset = 0
        while True:
            page = soup_of(f"{SITE}/search_category_list.php?I={offset}&&C=3&S=2&sc2={s2}")
            rows = 0
            for tr in page.find_all("tr"):
                link = tr.find("a", href=re.compile(r"rev\.php\?no=\d+"))
                cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                if not link or len(cells) < 3:
                    continue
                q = parse_qs(urlsplit(link["href"]).query)
                m = RELEASE.search(cells[2])
                out.setdefault(q["no"][0], {
                    "no": q["no"][0], "sid": q.get("sid", ["1"])[0], "name": cells[0], "model": cells[1],
                    "release": f"{m.group(1)}-{int(m.group(2)):02d}" if m else "", "category": label, "sc2": s2,
                })
                rows += 1
            nxt = page.find("a", href=re.compile(rf"\?I={offset + 25}&&C=3&S=2&sc2={s2}$"))
            if not rows or not nxt:
                break
            offset += 25
        print(f"  sc2 {s2} {label}: total {len(out)}", flush=True)
    write_jsonl(MODELS, sorted(out.values(), key=lambda r: r["release"], reverse=True))
    print(f"models {len(out)}")


def parse(html: str, base: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"].strip())
        if re.search(r"/manual\.pdf\?|\.pdf$", urlsplit(href).path + ("?" if urlsplit(href).query else ""), re.I):
            row = a.find_parent("tr")
            links.append({"href": href, "label": a.get_text(" ", strip=True),
                          "row": row.get_text(" | ", strip=True) if row else ""})
    text = soup.get_text(" ", strip=True)
    m = re.search(r"形名[:：]\s*([^\s/]+)", text)
    return {"links": links, "shown_model": m.group(1) if m else ""}


def fetch(args: argparse.Namespace) -> None:
    c = client()
    allm = load_jsonl(MODELS)
    done = {p["no"] for p in load_jsonl(PAGES) if p["status"] in (200, 404, "robots")}
    chosen = [m for m in allm if not args.since or (m["release"] and m["release"] >= args.since)]
    todo = [m for m in chosen if m["no"] not in done]
    print(f"since {args.since or '-'}: {len(chosen)} models, to fetch {len(todo)}", flush=True)
    lock = threading.Lock()

    def one(m):
        try:
            resp = c.post(f"{SITE}/rev.php", data={"no": m["no"], "sid": m["sid"], "YN": "Y"})  # 「同意して次へ」
        except RobotsDisallowed:
            rec = {"no": m["no"], "model": m["model"], "status": "robots", "links": []}
        except requests.RequestException as exc:
            print(f"network error {m['model']}: {type(exc).__name__}", flush=True)
            time.sleep(15)
            return None
        else:
            if resp.status_code in (403, 429) or resp.status_code >= 500:
                print(f"status {resp.status_code} on {m['model']}", flush=True)
                time.sleep(60)
                return "blocked"
            rec = {"no": m["no"], "model": m["model"], "status": resp.status_code,
                   **(parse(decode(resp), resp.url) if resp.status_code == 200 else {"links": []}), "fetched_at": now()}
        with lock, PAGES.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return None

    run_parallel(todo, one)
    print("fetch complete", flush=True)


def normalize(model: str) -> str:
    import unicodedata
    value = re.sub(r"\s+", "", unicodedata.normalize("NFKC", model)).upper()
    m = re.search(r"\((\w{1,2})\)$", value)  # GR-A470GSK(W) のような色表記
    return value[: m.start()] if m else value


def build(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")  # 同意Cookieを持たない状態でURLの有効性を確かめる
    meta = {m["no"]: m for m in load_jsonl(MODELS)}
    pages = list({p["no"]: p for p in load_jsonl(PAGES)}.values())
    url_models = defaultdict(set)
    for p in pages:
        for l in p.get("links", []):
            url_models[l["href"]].add(p["model"])
    rows, anomalies, stats = [], [], Counter()
    for p in pages:
        stats[f"page_status_{p['status']}"] += 1
        if p["status"] != 200 or not p.get("links"):
            anomalies.append({"type": "no_manual_links" if p["status"] == 200 else "page_not_200",
                              "model": p["model"], "detail": p["status"], "url": f"{SITE}/rev.php?no={p['no']}"})
            continue
        if p.get("shown_model") and squash(p["shown_model"]) != squash(p["model"]):
            anomalies.append({"type": "shown_model_differs", "model": p["model"], "detail": p["shown_model"], "url": ""})
        for l in {l["href"]: l for l in p["links"]}.values():
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": meta.get(p["no"], {}).get("category", ""),
                "model_raw": p["model"], "model_normalized": normalize(p["model"]), "title": l["label"], "url": l["href"],
                "url_type": "pdf", "source_method": "crawl", "first_seen": "", "http_status": "", "checked_at": "",
                "model_unconfirmed": "0", "discontinued": "",
            })
    statuses = check_urls(c, [r["url"] for r in rows], stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    for url, ms in url_models.items():
        if len(ms) > 1:
            anomalies.append({"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": url})
    write_rows(ROWS, rows)
    write_anomalies(ANOMALIES, anomalies)
    years = Counter((meta.get(p["no"], {}).get("release") or "unknown")[:4] for p in pages)
    stats.update(rows=len(rows), pages=len(pages), unique_urls=len({r["url"] for r in rows}),
                 models_with_manual=len({r["model_raw"] for r in rows}))
    stats.update({f"anomaly_{k}": v for k, v in Counter(a["type"] for a in anomalies).items()})
    stats.update({f"http_{k or 'blank'}": v for k, v in Counter(r["http_status"] for r in rows).items()})
    summary = {"stats": dict(sorted(stats.items())), "release_years": dict(sorted(years.items())),
               "titles_top": Counter(r["title"] for r in rows).most_common(20)}
    (RAW / f"{KEY}_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    sub.add_parser("models").set_defaults(func=models)
    f = sub.add_parser("fetch")
    f.add_argument("--since", default="")
    f.set_defaults(func=fetch)
    sub.add_parser("build").set_defaults(func=build)
    args = p.parse_args()
    NOTES.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()

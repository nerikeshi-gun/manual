"""シャープ（jp.sharp / cs.sharp.co.jp）の取説URL収集。

    python -m collector.sharp enumerate
    python -m collector.sharp fetch
    python -m collector.sharp build
    python -m collector.sharp verify

取説一覧（cs.sharp.co.jp/select/downloadInfo）は、利用規約ページ（select/download?productId=）で
「同意して次へ」を押した後に表示される。規約への同意はユーザーの承認済み（2026-11-13）。
同意と表示対象の型番はセッションに保持されるため、取得は1本の接続で順に行う。
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from collector.combine import COLUMNS
from collector.polite import PoliteClient, RobotsDisallowed

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "output" / "raw"
NOTES = ROOT / "output" / "notes"
MODELS = RAW / "sharp_models.jsonl"
PAGES = RAW / "sharp_pages.jsonl"
ROWS = RAW / "sharp_manuals.csv"
ANOMALIES = RAW / "sharp_anomalies.csv"
SAMPLE = NOTES / "sharp_verify_sample.csv"
LOG = ROOT / "output" / "logs" / "sharp_requests.log"

SITE = "https://jp.sharp"
CS = "https://cs.sharp.co.jp/select"
MAKER = "シャープ"
DOMAIN = "家電"
JST = timezone(timedelta(hours=9))
KISYU = re.compile(r'"kisyu"\s*:\s*"([^"]+)"')
RELEASE = re.compile(r"[（(](\d{4})年(\d{1,2})月発売[）)]")


_client: PoliteClient | None = None


def client() -> PoliteClient:
    global _client
    if _client is None:
        # 規約同意と表示中の型番はセッション単位なので、スレッドごとに別セッションにする
        _client = PoliteClient(log_path=LOG, session_per_thread=True)
    return _client


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def enumerate_models(_: argparse.Namespace) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    c = client()
    soup = BeautifulSoup(c.get(f"{SITE}/support/download.html").content, "lxml")
    cats: dict[str, str] = {}
    singles: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href, label = a["href"], a.get_text(" ", strip=True)
        m = re.match(r"^/support/([^/]+)/download\.html$", href)
        if m:
            cats.setdefault(m.group(1), label)
            continue
        m = re.search(r"cs\.sharp\.co\.jp/select/download\?productId=([^&#]+)", href)
        if m:
            singles.setdefault(m.group(1), label)
    print(f"categories {len(cats)}, single-model links {len(singles)}", flush=True)

    models: dict[str, dict] = {}
    missing: list[str] = []
    for slug, label in cats.items():
        found: list[str] = []
        try:
            js = c.get(f"{SITE}/support/{slug}/js/dl_katalist.js")
            if js.status_code == 200:
                found = KISYU.findall(js.content.decode("utf-8-sig", errors="replace"))
        except (RobotsDisallowed, requests.RequestException):
            pass
        if not found:  # 一覧データが無いカテゴリは、ページ内の productId リンクから拾う
            page = c.get(f"{SITE}/support/{slug}/download.html")
            found = re.findall(r"productId=([A-Za-z0-9\-_./%]+)", page.text)
            if not found:
                missing.append(f"{slug}\t{label}")
        for kisyu in found:
            models.setdefault(kisyu, {"model": kisyu, "category": label, "slug": slug})
        print(f"  {slug}: {len(found)}", flush=True)
    for kisyu, label in singles.items():
        models.setdefault(kisyu, {"model": kisyu, "category": label, "slug": ""})

    with MODELS.open("w", encoding="utf-8") as f:
        for rec in models.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    summary = {"categories": len(cats), "models": len(models), "categories_without_list": missing}
    (RAW / "sharp_enumerate_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def parse_info(html: bytes, base: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    m = RELEASE.search(text)
    release = f"{m.group(1)}-{int(m.group(2)):02d}" if m else ""
    shown = ""
    head = re.search(r"形名\s*/?\s*([A-Z0-9\-_/．.]+)\s*[（(]", soup.get_text(" / ", strip=True))
    if head:
        shown = head.group(1)
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:")):
            continue
        absolute = urljoin(base, href)
        host = urlsplit(absolute).netloc
        if "sharp" not in host or "acrobat" in absolute or "adobe" in absolute:
            continue
        path = urlsplit(absolute).path.lower()
        if not (path.endswith(".pdf") or "/manual/" in path or "/doc/" in path):
            continue
        row = a.find_parent("tr")
        links.append({"href": absolute, "label": a.get_text(" ", strip=True),
                      "row": row.get_text(" | ", strip=True) if row else ""})
    return {"release": release, "shown_model": shown, "links": links,
            "no_data": ("該当" in text and "ありません" in text) and not links}


def fetch_pages(args: argparse.Namespace) -> None:
    c = client()
    models = load_jsonl(MODELS)
    done = {r["model"] for r in load_jsonl(PAGES) if r["status"] in (200, 404, "robots")}
    todo = [m for m in models if m["model"] not in done]
    if args.sample:
        todo = random.Random(20261113).sample(todo, min(args.sample, len(todo)))
    print(f"models {len(models)}, done {len(done)}, to fetch {len(todo)}", flush=True)
    import threading
    from concurrent.futures import ThreadPoolExecutor
    lock = threading.Lock()
    blocked = Counter()

    def one(m: dict) -> None:
        terms_url = f"{CS}/download?productId={quote(m['model'], safe='')}"
        try:
            terms = c.get(terms_url)
            if terms.status_code == 200 and "同意して次へ" in terms.text:
                info_resp = c.get(f"{CS}/downloadInfo")  # 「同意して次へ」
                status = info_resp.status_code
                info = parse_info(info_resp.content, info_resp.url) if status == 200 else {}
            else:
                status = terms.status_code
                info = parse_info(terms.content, terms.url) if status == 200 else {}
        except RobotsDisallowed as exc:
            rec = {"model": m["model"], "status": "robots", "url": str(exc)}
        except requests.RequestException as exc:
            print(f"network error {m['model']}: {type(exc).__name__}", flush=True)
            time.sleep(15)
            return
        else:
            if status in (403, 429) or status >= 500:
                with lock:
                    blocked["n"] += 1
                print(f"status {status} on {m['model']}", flush=True)
                time.sleep(60)
                return
            rec = {"model": m["model"], "status": status, **info,
                   "fetched_at": datetime.now(JST).isoformat(timespec="seconds")}
        with lock, PAGES.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=2) as pool:
        for i, _ in enumerate(pool.map(one, todo), 1):
            if blocked["n"] >= 5:
                print("stopping: repeated blocks", flush=True)
                pool.shutdown(cancel_futures=True)
                sys.exit(3)
            if i % 200 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
    print("fetch complete", flush=True)


SIZE = re.compile(r"\s*[（(]?\s*[\d.,]+\s*[KMG]B\s*[）)]?\s*$", re.I)
COLOR_SUFFIX = re.compile(r"-([A-Z]{1,2})$")
COLOR_CODES = {"W", "B", "S", "N", "C", "R", "P", "H", "T", "G", "A", "K"}


def squash(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFKC", value).upper())


def normalize(model: str) -> str:
    """NFKC・空白除去・大文字化。末尾の色記号（-W, -B など）を除く。"""
    value = re.sub(r"\s+", "", unicodedata.normalize("NFKC", model)).upper()
    m = COLOR_SUFFIX.search(value)
    if m and m.group(1) in COLOR_CODES and len(value) - len(m.group(0)) >= 4:
        return value[: m.start()]
    return value


def url_kind(url: str) -> str | None:
    path = urlsplit(url).path.lower()
    if path.endswith(".pdf"):
        return "pdf"
    if path.endswith((".html", ".htm", "/")):
        return "html"
    return None  # CADデータ（.dxf）など、取説ではないファイル


def check_urls(c: PoliteClient, urls: list[str], stats: Counter) -> dict[str, tuple[str, str]]:
    """HEAD（拒否時のみRange付きGET）で生存確認する。2本並行、送信間隔はクライアント側で1秒以上。"""
    from concurrent.futures import ThreadPoolExecutor

    def one(url: str) -> tuple[str, tuple[str, str]]:
        now = lambda: datetime.now(JST).isoformat(timespec="seconds")
        if not c.can_fetch(url):
            stats["urls_robots_disallowed"] += 1
            return url, ("", "")
        try:
            return url, (str(c.head_or_range(url).status_code), now())
        except requests.RequestException as exc:
            return url, (type(exc).__name__, now())

    with ThreadPoolExecutor(max_workers=2) as pool:
        return dict(pool.map(one, urls))


def build(_: argparse.Namespace) -> None:
    c = client()
    models = {m["model"]: m for m in load_jsonl(MODELS)}
    pages = list({p["model"]: p for p in load_jsonl(PAGES)}.values())
    url_models: dict[str, set[str]] = defaultdict(set)
    for p in pages:
        for link in p.get("links", []):
            url_models[link["href"].split("?")[0]].add(p["model"])
    rows, anomalies = [], []
    stats: Counter = Counter()
    for p in pages:
        model = p["model"]
        stats[f"page_status_{p['status']}"] += 1
        if p["status"] != 200:
            anomalies.append({"type": "page_not_200", "model": model, "detail": p["status"], "url": ""})
            continue
        if not p.get("links"):
            anomalies.append({"type": "no_manual_links", "model": model, "detail": p.get("release", ""), "url": ""})
            continue
        if p.get("shown_model") and squash(p["shown_model"]) != squash(model):
            anomalies.append({"type": "shown_model_differs", "model": model, "detail": p["shown_model"], "url": ""})
        seen = set()
        for link in p["links"]:
            url = link["href"].split("?")[0]  # productId クエリは閲覧元の型番で、取説そのものの識別子ではない
            if url in seen:
                continue
            seen.add(url)
            title = SIZE.sub("", link["label"]).strip()
            kind = url_kind(url)
            if kind is None:
                anomalies.append({"type": "non_document_file", "model": model, "detail": title, "url": url})
                continue
            if len(url_models[url]) > 1:
                stats["rows_on_shared_url"] += 1
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": models.get(model, {}).get("category", ""),
                "model_raw": model, "model_normalized": normalize(model), "title": title, "url": url,
                "url_type": kind, "source_method": "api", "first_seen": "", "http_status": "",
                "checked_at": "", "model_unconfirmed": "0", "discontinued": "",
            })
    statuses = check_urls(c, sorted({r["url"] for r in rows}), stats)
    for r in rows:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    for url, ms in url_models.items():
        if len(ms) > 1:
            anomalies.append({"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": url})
    with ROWS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows)
    with ANOMALIES.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["type", "model", "detail", "url"])
        w.writeheader()
        w.writerows(anomalies)
    stats.update(rows=len(rows), pages=len(pages), unique_urls=len({r["url"] for r in rows}),
                 models_with_manual=len({r["model_raw"] for r in rows}),
                 normalized_changed=sum(r["model_raw"] != r["model_normalized"] for r in rows))
    stats.update({f"anomaly_{k}": v for k, v in Counter(a["type"] for a in anomalies).items()})
    stats.update({f"http_{k or 'blank'}": v for k, v in Counter(r["http_status"] for r in rows).items()})
    years = Counter((p.get("release") or "unknown")[:4] for p in pages)
    summary = {"stats": dict(sorted(stats.items())), "titles_top": Counter(r["title"] for r in rows).most_common(25),
               "release_years": dict(sorted(years.items()))}
    (RAW / "sharp_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def verify(_: argparse.Namespace) -> None:
    with ROWS.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    sample = random.Random(20261113).sample(rows, min(50, len(rows)))
    out = []
    for r in sample:
        name = urlsplit(r["url"]).path.rsplit("/", 1)[-1]
        out.append({"model_raw": r["model_raw"], "title": r["title"], "file_name": name,
                    "filename_check": "match" if squash(r["model_raw"]) in squash(name) else "mismatch",
                    "url": r["url"], "pdf_model_by_hand": ""})
    with SAMPLE.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(Counter(x["filename_check"] for x in out))
    for x in out:
        if x["filename_check"] == "mismatch":
            print(x["model_raw"], "|", x["title"], "|", x["file_name"])


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    sub.add_parser("enumerate").set_defaults(func=enumerate_models)
    f = sub.add_parser("fetch")
    f.add_argument("--sample", type=int, default=0)
    f.set_defaults(func=fetch_pages)
    sub.add_parser("build").set_defaults(func=build)
    sub.add_parser("verify").set_defaults(func=verify)
    args = p.parse_args()
    NOTES.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()

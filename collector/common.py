"""各社の収集スクリプトで共通に使う処理。"""
from __future__ import annotations

import csv
import json
import re
import threading
import unicodedata
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from collector.combine import COLUMNS
from collector.polite import PoliteClient, RobotsDisallowed

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "output" / "raw"
NOTES = ROOT / "output" / "notes"
LOGS = ROOT / "output" / "logs"
JST = timezone(timedelta(hours=9))


def now() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, items) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def squash(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFKC", value or "").upper())


def decode(resp: requests.Response) -> str:
    """meta charset を優先して本文を文字列にする（requests の推定は日本語サイトで外れることがある）。"""
    head = resp.content[:3000].lower()
    for enc in ("shift_jis", "euc-jp", "utf-8"):
        if enc.encode() in head or (enc == "shift_jis" and b"sjis" in head):
            return resp.content.decode("cp932" if enc == "shift_jis" else enc, errors="replace")
    return resp.content.decode("utf-8", errors="replace")


def check_urls(c: PoliteClient, urls, stats: Counter, workers: int = 2) -> dict[str, tuple[str, str]]:
    """HEAD（拒否時のみRange付きGET）で生存確認。robots.txt で不可なら確認しない（空欄）。"""
    def one(url: str):
        if not c.can_fetch(url):
            stats["urls_robots_disallowed"] += 1
            return url, ("", "")
        try:
            return url, (str(c.head_or_range(url).status_code), now())
        except RobotsDisallowed:
            stats["urls_robots_disallowed"] += 1
            return url, ("", "")
        except requests.RequestException as exc:
            return url, (type(exc).__name__, now())

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(one, sorted(set(urls))))


def write_rows(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows)


def write_anomalies(path: Path, anomalies: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["type", "model", "detail", "url"])
        w.writeheader()
        w.writerows(anomalies)


def run_parallel(items, fn, workers: int = 2, progress_every: int = 200, max_blocked: int = 5):
    """fn(item) を並行実行。fn が 'blocked' を返した回数が max_blocked に達したら止める。"""
    blocked = Counter()
    lock = threading.Lock()

    def wrap(item):
        result = fn(item)
        if result == "blocked":
            with lock:
                blocked["n"] += 1
        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, _ in enumerate(pool.map(wrap, items), 1):
            if blocked["n"] >= max_blocked:
                pool.shutdown(cancel_futures=True)
                raise SystemExit("stopping: repeated blocks or server errors")
            if i % progress_every == 0:
                print(f"  {i}/{len(items)}", flush=True)


def scan_catalog(c: PoliteClient, seeds: list[str], prefixes: tuple[str, ...], known: dict[str, str],
                 max_pages: int = 400, exclude: tuple[str, ...] = ("/support/",)) -> tuple[set[str], int]:
    """製品カタログ（サポート以外のページ）を同一ホスト・指定パス配下に限って巡回し、
    既知の型番（squash 済み → 元表記）のうち、ページ本文やリンクに現れたものを返す。

    色記号付きの表記（R-HZC54A-W など）は、末尾の -英字1〜2字を除いた形でも照合する。
    """
    host = urlsplit(seeds[0]).netloc
    queue, seen, found, pages = deque(seeds), set(seeds), set(), 0
    token = re.compile(r"(?<![A-Z0-9])([A-Z]{1,5}-?[A-Z0-9]{2,}(?:-[A-Z0-9]{1,4})?)(?![A-Z0-9])")
    while queue and pages < max_pages:
        url = queue.popleft()
        try:
            resp = c.get(url)
        except (RobotsDisallowed, requests.RequestException):
            continue
        if resp.status_code != 200 or "html" not in resp.headers.get("content-type", ""):
            continue
        pages += 1
        html = decode(resp)
        for t in token.findall(unicodedata.normalize("NFKC", html).upper()):
            for cand in (t, re.sub(r"-[A-Z]{1,2}$", "", t)):
                key = squash(cand)
                if key in known:
                    found.add(known[key])
        for a in BeautifulSoup(html, "lxml").find_all("a", href=True):
            nxt = urljoin(resp.url, a["href"])
            parts = urlsplit(nxt)
            nxt = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
            if parts.netloc != host or nxt in seen or not parts.path.startswith(prefixes):
                continue
            if any(x in parts.path for x in exclude) or not parts.path.endswith(("/", ".html")):
                continue
            seen.add(nxt)
            queue.append(nxt)
    return found, pages

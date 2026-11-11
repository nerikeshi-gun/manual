"""パナソニック（panasonic.jp）の取説URL収集。

使い方（順に実行。enumerate と fetch は途中再開できる）:
    python -m collector.panasonic enumerate
    python -m collector.panasonic fetch [--sample N]
    python -m collector.panasonic build
    python -m collector.panasonic verify

取説PDFの置き場所は robots.txt で Disallow のため、PDFには一切アクセスしない。
PDFのURLは、許可されているサポートページのHTMLから読み取るだけにする。
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

from collector.polite import PoliteClient, RobotsDisallowed

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
RAW = OUT / "raw"
NOTES = OUT / "notes"
MODELS = RAW / "panasonic_models.jsonl"
PAGES = RAW / "panasonic_pages.jsonl"
ANOMALIES = RAW / "panasonic_anomalies.csv"
CSV_PATH = OUT / "manuals.csv"
SAMPLE = NOTES / "panasonic_verify_sample.csv"
LOG = OUT / "logs" / "panasonic_requests.log"

SITE = "https://panasonic.jp"
API = "https://1006091-adobeiopisc.adobeioruntime.net/api/v1/web/PanasonicCIF-2.0.0/io"
MAKER = "パナソニック"
DOMAIN = "家電"
JST = timezone(timedelta(hours=9))
PAGE_SIZE = 100  # 500 は API が 400 を返す。100 は実測で可

SEARCH_QUERY = """query SiteSearch($keyword:String $filter:SiteSearchFilterInput $limit:Int $offset:Int $relatedKeywordLimit:Int $sort_key:String $sort_order:SortEnum){
 siteSearch(keyword:$keyword filter:$filter limit:$limit offset:$offset relatedKeywordLimit:$relatedKeywordLimit sort_key:$sort_key sort_order:$sort_order){ total{support} supports{status_icons name sku release_date url} }}"""
BASE_FILTER = {"is_plan": False, "is_instructions": True, "type": "5"}

COLUMNS = [
    "maker", "domain", "product_category", "model_raw", "model_normalized", "title", "url",
    "url_type", "source_method", "first_seen", "http_status", "checked_at",
    "model_unconfirmed", "discontinued",
]


def client() -> PoliteClient:
    return PoliteClient(log_path=LOG)


def search(c: PoliteClient, filt: dict, offset: int, order: str = "DESC") -> tuple[int, list[dict]]:
    variables = {
        "keyword": "", "filter": filt, "limit": PAGE_SIZE, "offset": offset,
        "relatedKeywordLimit": 0, "sort_key": "release_date", "sort_order": order,
    }
    for attempt in range(4):
        try:
            resp = c.get(API, params={
                "query": SEARCH_QUERY,
                "variables": json.dumps(variables, ensure_ascii=False),
                "operationName": "SiteSearch",
            })
            data = resp.json()
            node = (data.get("data") or {}).get("siteSearch")
            if resp.status_code == 200 and node and not data.get("errors"):
                return node["total"]["support"] or 0, node["supports"] or []
        except (requests.RequestException, ValueError):
            pass
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"search failed: {filt} offset={offset}")


def scan(c: PoliteClient, filt: dict, seen: dict, label: str, uid: str, order: str = "DESC") -> tuple[int, int]:
    """filt に一致する全ページを読み、seen に追加する。(API件数, このスキャンで見えたユニーク数)。"""
    offset, total, local = 0, None, set()
    while total is None or offset < total:
        total, items = search(c, filt, offset, order)
        if not items:
            break
        for item in items:
            local.add(item["sku"])
            rec = seen.setdefault(item["sku"], {**item, "category_uid": uid, "category_label": label, "n_categories": 0})
            rec["n_categories"] += 1
        offset += PAGE_SIZE
    return total or 0, len(local)


def enumerate_models(_: argparse.Namespace) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    c = client()
    soup = BeautifulSoup(c.get(f"{SITE}/support/manual.html").text, "lxml")
    cats: dict[str, str] = {}
    for a in soup.find_all("a", href=re.compile("narrowing_down=userManual")):
        uid = re.search(r"category_uid=([^&]+)", a["href"]).group(1)
        cats.setdefault(uid, a.get_text(" ", strip=True))
    print(f"categories: {len(cats)}", flush=True)

    seen: dict[str, dict] = {}
    short: list[tuple[str, int, int]] = []
    for i, (uid, label) in enumerate(cats.items(), 1):
        total, got = scan(c, {**BASE_FILTER, "category_uid": uid}, seen, label, uid)
        if got < total:
            short.append((label, total, got))
        if i % 25 == 0:
            print(f"  {i}/{len(cats)} categories, unique SKUs {len(seen)}", flush=True)

    global_total, _n = search(c, BASE_FILTER, 0)[0], 0
    print(f"category union {len(seen)} / global total {global_total}; short pages {len(short)}", flush=True)
    if len(seen) < global_total or short:
        for order in ("DESC", "ASC"):
            before = len(seen)
            scan(c, BASE_FILTER, seen, "", "", order)
            print(f"  global scan {order}: +{len(seen) - before}", flush=True)

    with MODELS.open("w", encoding="utf-8") as f:
        for rec in seen.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    summary = {"categories": len(cats), "unique_skus": len(seen), "global_total": global_total,
               "short_categories": short[:50]}
    (RAW / "panasonic_enumerate_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "short_categories"}, ensure_ascii=False), flush=True)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def parse_support(html: str, base: str) -> tuple[list[dict], int]:
    soup = BeautifulSoup(html, "lxml")
    section = soup.find(id="manual")
    links = []
    if section is not None:
        for a in section.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "javascript:")):
                continue
            links.append({"href": urljoin(base, href), "label": a.get_text(" ", strip=True)})
    other_pdf = sum(
        1 for a in soup.find_all("a", href=True)
        if a["href"].lower().endswith(".pdf") and (section is None or section not in a.parents)
    )
    return links, other_pdf


def follow(c: PoliteClient, url: str, max_hops: int = 4) -> tuple[requests.Response, str]:
    """panasonic.jp 内のリダイレクトだけを1ホップずつ追う（各ホップに制限が掛かる）。"""
    resp = c.get(url, allow_redirects=False)
    for _ in range(max_hops):
        location = resp.headers.get("location")
        if resp.status_code not in (301, 302, 303, 307, 308) or not location:
            break
        target = urljoin(url, location)
        if urlsplit(target).netloc.lower() != "panasonic.jp":
            return resp, target
        url = target
        resp = c.get(url, allow_redirects=False)
    return resp, url


def keep_awake() -> None:
    """このプロセスが動いている間だけWindowsのアイドルスリープを抑止する。設定は変えない。"""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)


def fetch_pages(args: argparse.Namespace) -> None:
    keep_awake()
    c = client()
    models = load_jsonl(MODELS)
    done_rows = load_jsonl(PAGES)
    done = {r["sku"] for r in done_rows if r["status"] in (200, 404, "robots")}
    cat_path: dict[str, str] = {
        r["category_uid"]: r["path_prefix"] for r in done_rows if r.get("path_prefix") and r["category_uid"]
    }
    random.Random(20261110).shuffle(models)
    if args.sample:
        models = models[: args.sample]
    todo = [m for m in models if m["sku"] not in done]
    print(f"models {len(models)}, already done {len(models) - len(todo)}, to fetch {len(todo)}", flush=True)

    blocked = 0
    with PAGES.open("a", encoding="utf-8") as out:
        for i, m in enumerate(todo, 1):
            sku = m["sku"]
            encoded = quote(sku, safe="")
            uid = m["category_uid"]
            prefix = cat_path.get(uid) if uid else None  # カテゴリ不明の機種は推測せず正規URLから辿る
            status, page_url, html = None, None, None
            try:
                if prefix:
                    r, page_url = follow(c, f"{SITE}/{prefix}/products/{encoded}/support.html")
                    status, html = r.status_code, r.text
                if status != 200:
                    r, page_url = follow(c, m["url"])
                    status, html = r.status_code, r.text
                    found = re.match(r"/([^/]+(?:/[^/]+)*?)/products/", urlsplit(page_url).path)
                    if status == 200 and found:
                        prefix = found.group(1)
                        if uid:
                            cat_path[uid] = prefix
            except RobotsDisallowed as exc:
                out.write(json.dumps({"sku": sku, "category_uid": m["category_uid"], "status": "robots", "page_url": str(exc), "links": []}, ensure_ascii=False) + "\n")
                out.flush()
                continue
            except requests.RequestException as exc:
                print(f"network error {sku}: {type(exc).__name__}", flush=True)
                time.sleep(15)
                continue  # 記録せず、次回の再開時に再試行する

            if status in (403, 429) or status >= 500:
                blocked += 1
                print(f"status {status} on {sku}; backing off ({blocked})", flush=True)
                if blocked >= 5:
                    print("stopping: repeated blocks or server errors", flush=True)
                    sys.exit(3)
                time.sleep(60 * blocked)
                continue
            blocked = 0

            links, other_pdf = parse_support(html, page_url) if status == 200 else ([], 0)
            out.write(json.dumps({
                "sku": sku, "category_uid": m["category_uid"], "status": status, "page_url": page_url,
                "path_prefix": prefix, "links": links, "other_pdf_links": other_pdf,
                "fetched_at": datetime.now(JST).isoformat(timespec="seconds"),
            }, ensure_ascii=False) + "\n")
            out.flush()
            if i % 200 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
    print("fetch complete", flush=True)


SIZE_SUFFIX = re.compile(r"\s*[（(]\s*[\d.,]+\s*[KMGkmg]?B\s*/\s*PDF\s*[）)]\s*$")
BRACKET = re.compile(r"[［\[]([^］\]]*)[］\]]")
COLOR_SUFFIX = re.compile(r"-([A-Z]{1,2})$")
COLOR_CODES = {"W", "K", "H", "N", "C", "S", "T", "R", "A", "P", "G", "B", "D", "V", "CK", "HK", "PK", "WK"}


OLD_STYLE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9\-/、,_ ]*?)\s*[（(]([^（）()]*[^\x00-\x7f][^（）()]*)[）)]$")
JAPANESE = re.compile(r"[぀-ヿ一-鿿]")


def clean_title(label: str) -> tuple[str, str]:
    """ラベルを (タイトル, ラベル中の型番表記) に分ける。

    新形式: 「取扱説明書［NA-FW10K2］」 → ("取扱説明書", "NA-FW10K2")
    旧形式: 「SQ-LD100-K(取扱説明書)」 → ("取扱説明書", "SQ-LD100-K")
    型番だけのラベル（「SDR-S7」）はタイトル不明として ("", "SDR-S7") を返す（推測しない）。
    """
    text = SIZE_SUFFIX.sub("", label).strip()
    match = BRACKET.search(text)
    if match:
        return (BRACKET.sub("", text).strip() or text), match.group(1).strip()
    old = OLD_STYLE.match(text)
    if old:
        return old.group(2).strip(), old.group(1).strip()
    if not JAPANESE.search(text) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-/、,_ .]*", text):
        return "", text
    return text, ""


def squash(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFKC", value).upper())


def normalize(sku: str, _all_skus: set[str] | None = None) -> str:
    """NFKC・空白除去・大文字化し、末尾の色記号（-W、-K など一覧にあるもの）を除く。年度記号は残す。"""
    value = re.sub(r"\s+", "", unicodedata.normalize("NFKC", sku)).upper()
    match = COLOR_SUFFIX.search(value)
    if match and match.group(1) in COLOR_CODES:
        return value[: match.start()]
    return value


def label_anomaly(sku: str, bracket: str) -> str | None:
    if not bracket or squash(bracket) == squash(sku):
        return None
    if re.search(r"[、,，/／・_]", bracket):
        return "multi_model_label"
    if "シリーズ" in bracket:
        return "series_label"
    if squash(normalize(bracket)) == squash(normalize(sku)):
        return None  # 色記号の有無だけの違い
    return "label_differs_from_sku"


def is_pdf(url: str) -> bool:
    return urlsplit(url).path.lower().endswith(".pdf")


def build(_: argparse.Namespace) -> None:
    c = client()
    models = {m["sku"]: m for m in load_jsonl(MODELS)}
    pages = list({p["sku"]: p for p in load_jsonl(PAGES)}.values())  # 再取得した機種は最新の記録を使う
    upper_skus = {re.sub(r"\s+", "", unicodedata.normalize("NFKC", s)).upper() for s in models}
    url_to_skus: dict[str, set[str]] = defaultdict(set)
    for p in pages:
        for link in p.get("links", []):
            url_to_skus[link["href"]].add(p["sku"])

    rows: list[dict] = []
    anomalies: list[dict] = []
    statuses: dict[str, tuple[str, str]] = {}
    stats: Counter = Counter()
    for p in pages:
        sku, m = p["sku"], models.get(p["sku"], {})
        stats[f"page_status_{p['status']}"] += 1
        if p["status"] != 200:
            anomalies.append({"type": "page_not_200", "sku": sku, "detail": p["status"], "url": p.get("page_url", "")})
            continue
        if not p["links"]:
            anomalies.append({"type": "no_manual_links", "sku": sku, "detail": f"other_pdf={p.get('other_pdf_links', 0)}", "url": p["page_url"]})
        seen_urls = set()
        for link in p["links"]:
            url = link["href"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            title, bracket = clean_title(link["label"])
            kind = label_anomaly(sku, bracket)
            if kind:
                anomalies.append({"type": kind, "sku": sku, "detail": bracket, "url": url})
            if not title:
                stats["rows_title_unknown"] += 1
            if len(url_to_skus[url]) > 1:
                stats["rows_on_shared_url"] += 1
            if not is_pdf(url):
                anomalies.append({"type": "non_pdf_link", "sku": sku, "detail": link["label"], "url": url})
            if url not in statuses:
                if c.can_fetch(url):
                    try:
                        resp = c.head_or_range(url)
                        statuses[url] = (str(resp.status_code), datetime.now(JST).isoformat(timespec="seconds"))
                    except requests.RequestException as exc:
                        statuses[url] = (type(exc).__name__, datetime.now(JST).isoformat(timespec="seconds"))
                else:
                    statuses[url] = ("", "")
                    stats["urls_robots_disallowed"] += 1
            http_status, checked_at = statuses[url]
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": m.get("category_label", ""),
                "model_raw": sku, "model_normalized": normalize(sku, upper_skus), "title": title,
                "url": url, "url_type": "pdf" if is_pdf(url) else "html", "source_method": "crawl",
                "first_seen": "", "http_status": http_status, "checked_at": checked_at,
                "model_unconfirmed": "0",
                "discontinued": "1" if "生産終了" in (m.get("status_icons") or []) else "0",
            })

    for url, skus in url_to_skus.items():
        if len(skus) > 1:
            anomalies.append({"type": "shared_url", "sku": " ".join(sorted(skus)[:20]), "detail": len(skus), "url": url})

    OUT.mkdir(exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with ANOMALIES.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, ["type", "sku", "detail", "url"])
        writer.writeheader()
        writer.writerows(anomalies)

    stats["rows"] = len(rows)
    stats["pages"] = len(pages)
    stats["unique_urls"] = len({r["url"] for r in rows})
    stats["skus_with_manual"] = len({r["model_raw"] for r in rows})
    stats["discontinued_rows"] = sum(r["discontinued"] == "1" for r in rows)
    stats["normalized_changed"] = sum(r["model_raw"] != r["model_normalized"] for r in rows)
    for kind, n in Counter(a["type"] for a in anomalies).items():
        stats[f"anomaly_{kind}"] = n
    summary = {
        "stats": dict(sorted(stats.items())),
        "titles_top": Counter(r["title"] for r in rows).most_common(25),
        "url_hosts": Counter(urlsplit(r["url"]).netloc for r in rows).most_common(),
    }
    (RAW / "panasonic_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def verify(_: argparse.Namespace) -> None:
    """PDFを開かずにできる代替照合。PDF本文との照合ではない。"""
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    labels = {}
    for p in load_jsonl(PAGES):
        for link in p.get("links", []):
            labels[(p["sku"], link["href"])] = link["label"]

    sample = random.Random(20261110).sample(rows, 50)
    out_rows = []
    for r in sample:
        label = labels.get((r["model_raw"], r["url"]), "")
        _, bracket = clean_title(label) if label else ("", "")
        name = urlsplit(r["url"]).path.rsplit("/", 1)[-1]
        model = squash(r["model_raw"])
        bracket_result = "no_model_in_label" if not bracket else ("match" if model in squash(bracket) else "mismatch")
        name_result = "match" if model in squash(name) else "mismatch"
        out_rows.append({
            "model_raw": r["model_raw"], "title": r["title"], "label_on_page": label, "label_check": bracket_result,
            "file_name": name, "filename_check": name_result, "url": r["url"], "pdf_model_by_hand": "",
        })
    with SAMPLE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, list(out_rows[0]))
        writer.writeheader()
        writer.writerows(out_rows)
    print(json.dumps({
        "label": Counter(x["label_check"] for x in out_rows),
        "filename": Counter(x["filename_check"] for x in out_rows),
    }, ensure_ascii=False))
    for x in out_rows:
        if x["label_check"] == "mismatch" or x["filename_check"] == "mismatch":
            print(x["model_raw"], "|", x["label_on_page"], "|", x["file_name"])


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)
    sub.add_parser("enumerate").set_defaults(func=enumerate_models)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--sample", type=int, default=0)
    fetch.set_defaults(func=fetch_pages)
    sub.add_parser("build").set_defaults(func=build)
    sub.add_parser("verify").set_defaults(func=verify)
    args = parser.parse_args()
    NOTES.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()

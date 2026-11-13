"""ソニー（support.sony.jp / www.sony.jp）の取説URL収集。

    python -m collector.sony models      # サポートサイトのサイトマップから全型番
    python -m collector.sony catalog     # 製品カタログ（ギャラリーJSON）から現行シリーズ
    python -m collector.sony fetch --phase current   # 現行品だけ（新しい順）
    python -m collector.sony fetch --phase rest      # 残り
    python -m collector.sony build
    python -m collector.sony verify

取説PDFは www.sony.com 上にあり、www.sony.com は robots.txt に403を返すため一切アクセスしない。
ヘルプガイド（helpguide.sony.net、HTML）は robots.txt が404のため生存確認を行う。
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from collector.combine import COLUMNS
from collector.polite import PoliteClient, RobotsDisallowed

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "output" / "raw"
NOTES = ROOT / "output" / "notes"
MODELS = RAW / "sony_models.jsonl"
CATALOG = RAW / "sony_catalog.jsonl"
PAGES = RAW / "sony_pages.jsonl"
ROWS = RAW / "sony_manuals.csv"
ANOMALIES = RAW / "sony_anomalies.csv"
SAMPLE = NOTES / "sony_verify_sample.csv"
LOG = ROOT / "output" / "logs" / "sony_requests.log"

SUPPORT = "https://support.sony.jp"
CATALOG_SITE = "https://www.sony.jp"
MAKER = "ソニー"
DOMAIN = "家電"
JST = timezone(timedelta(hours=9))
SKIP_SITEMAPS = ("misc", "documents", "downloads", "articles")
NOT_CATALOG = {
    "CorporateCruise", "Security", "accessibility", "app", "campaign-lineup", "dealer", "feature", "info",
    "line", "my-favorites", "overseas", "parts", "spot-map", "store", "support", "software",
}

_client: PoliteClient | None = None


def client() -> PoliteClient:
    global _client
    if _client is None:
        _client = PoliteClient(log_path=LOG)
    return _client


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, items) -> None:
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def models(_: argparse.Namespace) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    c = client()
    index = c.get(f"{SUPPORT}/electronics/gwtsitemapindex.xml").text
    out: dict[str, dict] = {}
    for sitemap in re.findall(r"<loc>([^<]+)", index):
        if any(k in sitemap for k in SKIP_SITEMAPS):
            continue
        resp = c.get(sitemap)
        if resp.status_code != 200:
            print(f"sitemap {resp.status_code}: {sitemap}", flush=True)
            continue
        for loc in re.findall(r"<loc>([^<]+)", resp.text):
            m = re.match(r"https://support\.sony\.jp/electronics/support/([^/]+)/([^/]+)/?$", loc)
            if m:
                out.setdefault(m.group(2), {"slug": m.group(2), "category_path": m.group(1), "url": loc})
    write_jsonl(MODELS, out.values())
    print(f"support models: {len(out)}", flush=True)


def catalog(_: argparse.Namespace) -> None:
    c = client()
    soup = BeautifulSoup(c.get(f"{CATALOG_SITE}/contents.html").content, "lxml")
    dirs = sorted({m.group(1) for a in soup.find_all("a", href=True)
                   for m in [re.match(r"(?:https?://www\.sony\.jp)?/([A-Za-z0-9_\-]+)/", a["href"])] if m} - NOT_CATALOG)
    items: list[dict] = []
    found_dirs, missing = [], []
    for d in dirs:
        endpoint = content_path = None
        for page in ("gallery/", "lineup/"):
            try:
                resp = c.get(f"{CATALOG_SITE}/{d}/{page}")
            except RobotsDisallowed:
                continue
            g = re.search(r'"getProductGalleryUrl"\s*:\s*"([^"]+)"', resp.text)
            cp = re.search(r'"contentPath"\s*:\s*"([^"]+)"', resp.text)
            if resp.status_code == 200 and g and cp:
                endpoint, content_path = g.group(1), cp.group(1)
                break
        if not endpoint:
            missing.append(d)
            continue
        data = c.get(urljoin(CATALOG_SITE, endpoint), params={"contentPath": content_path}).json()
        found_dirs.append(d)
        for p in data.get("products", []):
            url = p.get("learnMoreUrl") or ""
            m = re.search(r"/products/([^/?#]+)", url)
            items.append({
                "dir": d, "display": p.get("displayName"), "marketing": p.get("marketingName"),
                "model": m.group(1) if m else "", "url": url, "jan": p.get("slug"),
                "release": ms_date(p.get("releaseDate")), "retirement": ms_date(p.get("retirementDateTime")),
            })
        print(f"  {d}: {len(data.get('products', []))}", flush=True)
    write_jsonl(CATALOG, items)
    summary = {"catalog_dirs": found_dirs, "dirs_without_gallery": missing, "series": len(items)}
    (RAW / "sony_catalog_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


MODEL_TOKEN = re.compile(r"(?<![A-Z0-9])([A-Z]{2,6}-[A-Z0-9][A-Z0-9/]{1,14})(?![A-Z0-9])")


def tokens_in(html: str, support: set[str]) -> list[str]:
    """ページ内の型番らしい文字列のうち、サポートサイトに実在する型番だけを返す。"""
    found = {t.lower().rstrip("/") for t in MODEL_TOKEN.findall(html.upper())}
    return sorted(t for t in found if t in support)


def catalog_pages(_: argparse.Namespace) -> None:
    """ギャラリーで型番に一致しなかったシリーズと、ギャラリーのないカテゴリを、カタログの製品ページで補う。"""
    c = client()
    support = {m["slug"] for m in load_jsonl(MODELS)}
    items = load_jsonl(CATALOG)
    targets = current_targets()
    matched = {v["series"] for v in targets.values()}
    added = 0
    for item in items:
        if item.get("models") or not item["url"] or item["model"] in matched:
            continue
        try:
            resp = c.get(item["url"])
        except (RobotsDisallowed, requests.RequestException):
            continue
        item["models"] = tokens_in(resp.text, support) if resp.status_code == 200 else []
        added += len(item["models"])
    summary = json.loads((RAW / "sony_catalog_summary.json").read_text(encoding="utf-8"))
    extra_dirs = []
    for d in summary["dirs_without_gallery"]:
        product_codes: set[str] = set()
        for page in (f"{CATALOG_SITE}/{d}/", f"{CATALOG_SITE}/{d}/products/"):
            try:
                resp = c.get(page)
            except (RobotsDisallowed, requests.RequestException):
                continue
            if resp.status_code != 200:
                continue
            product_codes.update(re.findall(rf"/{re.escape(d)}/products/([A-Za-z0-9\-_]+)/", resp.text))
            for code in tokens_in(resp.text, support):
                product_codes.add(code.upper())
        for code in sorted(product_codes):
            items.append({"dir": d, "display": code, "marketing": "", "model": code, "url": f"{CATALOG_SITE}/{d}/products/{code}/",
                          "jan": None, "release": "", "retirement": "", "source": "products_page"})
        extra_dirs.append((d, len(product_codes)))
        print(f"  {d}: {len(product_codes)}", flush=True)
    write_jsonl(CATALOG, items)
    print(json.dumps({"models_from_series_pages": added, "dirs": extra_dirs}, ensure_ascii=False), flush=True)


def ms_date(value) -> str:
    try:
        if value is None or int(value) >= 9_000_000_000_000:
            return ""
        return datetime.fromtimestamp(int(value) / 1000, JST).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def series_pattern(model: str) -> re.Pattern:
    """カタログのシリーズ型番から、サポートサイトの個別型番を拾う正規表現。

    XRJ-A90K → xrj-48a90k, xrj-55a90k（画面サイズの挿入）
    ILCE-7M4 → ilce-7m4, ilce-7m4k（キット・色などの短い接尾辞）
    """
    m = model.lower()
    head, sep, tail = m.partition("-")
    sized = rf"{re.escape(head)}-\d{{2,3}}{re.escape(tail)}" if sep and tail and tail[0].isalpha() else None
    plain = rf"{re.escape(m)}(?:[a-z]{{0,2}}|-[a-z]{{1,2}})"
    return re.compile(rf"^(?:{plain}|{sized})$" if sized else rf"^{plain}$")


def current_targets() -> dict[str, dict]:
    """現行（retirement が未来または未設定）のシリーズに一致するサポート型番。"""
    support = {m["slug"]: m for m in load_jsonl(MODELS)}
    today = datetime.now(JST).strftime("%Y-%m-%d")
    hits: dict[str, dict] = {}
    for item in load_jsonl(CATALOG):
        if not item["model"] or (item["retirement"] and item["retirement"] <= today):
            continue
        pats = [series_pattern(item["model"])] + [series_pattern(x) for x in item.get("models", [])]
        for slug in support:
            if any(pat.match(slug) for pat in pats):
                prev = hits.get(slug)
                if prev is None or (item["release"] or "") > (prev["release"] or ""):
                    hits[slug] = {"series": item["model"], "release": item["release"], "dir": item["dir"]}
    return hits


TITLE_DATE = re.compile(r"公開日\s*[:：]\s*(\d{4}/\d{2}/\d{2})")
TITLE_SIZE = re.compile(r"\(\s*[\d.,]+\s*[KMG]B\s*\)|ファイルサイズが指定されていません。")


def parse_manuals(html: bytes, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"].strip())
        path = urlsplit(href).path.lower()
        if not ("/res/manuals/" in path or "helpguide.sony.net" in href or path.endswith(".pdf")):
            continue
        out.append({"href": href, "label": a.get_text(" ", strip=True)})
    return out


def fetch(args: argparse.Namespace) -> None:
    c = client()
    support = {m["slug"]: m for m in load_jsonl(MODELS)}
    targets = current_targets()
    done = {p["slug"] for p in load_jsonl(PAGES) if p["status"] in (200, 404, "robots")}
    if args.phase == "current":
        order = sorted(targets, key=lambda s: targets[s]["release"] or "", reverse=True)
    else:
        order = [s for s in support if s not in targets]
    todo = [s for s in order if s not in done]
    print(f"phase {args.phase}: targets {len(order)}, to fetch {len(todo)}", flush=True)
    lock = threading.Lock()
    blocked = Counter()

    def one(slug: str) -> None:
        m = support[slug]
        url = f"{m['url']}/manuals"
        try:
            resp = c.get(url)
        except RobotsDisallowed:
            rec = {"slug": slug, "status": "robots", "links": []}
        except requests.RequestException as exc:
            print(f"network error {slug}: {type(exc).__name__}", flush=True)
            return
        else:
            if resp.status_code in (403, 429) or resp.status_code >= 500:
                with lock:
                    blocked["n"] += 1
                print(f"status {resp.status_code} on {slug}", flush=True)
                time.sleep(60)
                return
            rec = {"slug": slug, "status": resp.status_code,
                   "links": parse_manuals(resp.content, resp.url) if resp.status_code == 200 else [],
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


def squash(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFKC", value).upper())


def normalize(model: str) -> str:
    """NFKC・大文字化。ソニーの型番は色を別型番にしない（サポート側は色なし）ため色記号処理はしない。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", model)).upper()


def build(_: argparse.Namespace) -> None:
    c = client()
    support = {m["slug"]: m for m in load_jsonl(MODELS)}
    targets = current_targets()
    pages = list({p["slug"]: p for p in load_jsonl(PAGES)}.values())
    url_models: dict[str, set[str]] = defaultdict(set)
    for p in pages:
        for link in p.get("links", []):
            url_models[link["href"]].add(p["slug"])
    rows, anomalies = [], []
    stats: Counter = Counter()
    for p in pages:
        slug = p["slug"]
        stats[f"page_status_{p['status']}"] += 1
        if p["status"] != 200:
            anomalies.append({"type": "page_not_200", "model": slug, "detail": p["status"], "url": ""})
            continue
        if not p["links"]:
            stats["pages_without_manuals"] += 1
            continue
        seen = set()
        for link in p["links"]:
            url = link["href"]
            if url in seen:
                continue
            seen.add(url)
            label = link["label"]
            title = TITLE_SIZE.sub("", TITLE_DATE.sub("", label)).replace("[PDF]", "").strip(" -")
            if len(url_models[url]) > 1:
                stats["rows_on_shared_url"] += 1
            rows.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": support[slug]["category_path"],
                "model_raw": slug.upper(), "model_normalized": normalize(slug), "title": title, "url": url,
                "url_type": "pdf" if urlsplit(url).path.lower().endswith(".pdf") else "html",
                "source_method": "sitemap", "first_seen": "", "http_status": "", "checked_at": "",
                "model_unconfirmed": "0", "discontinued": "0" if slug in targets else "",
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
                 models_with_manual=len({r["model_raw"] for r in rows}), current_targets=len(targets),
                 current_rows=sum(r["discontinued"] == "0" for r in rows))
    stats.update({f"anomaly_{k}": v for k, v in Counter(a["type"] for a in anomalies).items()})
    stats.update({f"http_{k or 'blank'}": v for k, v in Counter(r["http_status"] for r in rows).items()})
    summary = {"stats": dict(sorted(stats.items())), "titles_top": Counter(r["title"] for r in rows).most_common(25),
               "url_hosts": Counter(urlsplit(r["url"]).netloc for r in rows).most_common()}
    (RAW / "sony_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def check_urls(c: PoliteClient, urls: list[str], stats: Counter) -> dict[str, tuple[str, str]]:
    def one(url: str):
        now = datetime.now(JST).isoformat(timespec="seconds")
        if not c.can_fetch(url):
            stats["urls_robots_disallowed"] += 1
            return url, ("", "")
        try:
            return url, (str(c.head_or_range(url).status_code), now)
        except requests.RequestException as exc:
            return url, (type(exc).__name__, now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        return dict(pool.map(one, urls))


def verify(_: argparse.Namespace) -> None:
    with ROWS.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    labels = {(p["slug"].upper(), l["href"]): l["label"] for p in load_jsonl(PAGES) for l in p.get("links", [])}
    sample = random.Random(20261113).sample(rows, min(50, len(rows)))
    out = [{"model_raw": r["model_raw"], "title": r["title"], "label_on_page": labels.get((r["model_raw"], r["url"]), ""),
            "url": r["url"], "pdf_model_by_hand": ""} for r in sample]
    with SAMPLE.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"sample written: {len(out)}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    sub.add_parser("models").set_defaults(func=models)
    sub.add_parser("catalog").set_defaults(func=catalog)
    sub.add_parser("catalog_pages").set_defaults(func=catalog_pages)
    f = sub.add_parser("fetch")
    f.add_argument("--phase", choices=["current", "rest"], default="current")
    f.set_defaults(func=fetch)
    sub.add_parser("build").set_defaults(func=build)
    sub.add_parser("verify").set_defaults(func=verify)
    args = p.parse_args()
    NOTES.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()

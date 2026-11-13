"""パナソニック ハウジング（住宅設備・建材: www2.panasonic.biz Vカタ「図面・説明書 カテゴリ検索」）の取説URL収集。

入口: www2.panasonic.biz/jp/sumai/manual/（ご利用条件に同意の上で利用。条件は notice.html）
→ /scvb/a2A/zumenCategResult?CATEGORY_KAISO=/CTG005298/<分類>&CATEGORY_CD=...（GET, 公開ページ）
カテゴリは階層（goZumenCategoryKaiso のリンク）。「(N件)」の付く末端カテゴリで資料一覧が出る（20件/ページ、
listForm の START_CNT でページ送り）。各行: 名称・発売年月・品番（緑字）・「生産終了商品」表示・資料種別・PDF。
PDF は /ideacontout/... 上にあり robots.txt で Disallow のため、URLを記録するだけで生存確認はしない（http_status 空）。

    python -m collector.panasonic_housing run
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup

from collector.common import LOGS, NOTES, RAW, check_urls, decode, now, write_anomalies, write_jsonl, write_rows
from collector.polite import PoliteClient

ENTRY = "https://www2.panasonic.biz/jp/sumai/manual/"
RESULT = "https://www2.panasonic.biz/scvb/a2A/zumenCategResult"
MAKER, DOMAIN, KEY = "パナソニック ハウジング", "住設", "panasonic_housing"
KAISO = re.compile(r"goZumenCategoryKaiso\('(\d)',\s*'([^']+)',\s*'([^']+)'\)[^>]*>\s*(?:<[^>]+>\s*)*([^<]+)")
PDF_ARG = re.compile(r"ajaxJsonRegistUselog\('[^']*',\s*'([^']+)'\)")
MODEL_LIKE = re.compile(r"[○A-Z0-9][A-Z0-9○()\-/*＊.]{3,}")  # NFKC 後の品番（例 ○○KM6061(Z)EP, EDB1000M1）


def params_for(path: str) -> list[tuple[str, str]]:
    return [("CATEGORY_KAISO", path), ("hid_category_kbn", "1")] + [("CATEGORY_CD", c) for c in path.strip("/").split("/")]


def parse_rows(soup: BeautifulSoup, category: str) -> list[dict]:
    out = []
    for d in soup.select("div.module_check_batch3"):
        meisho, view = d.select_one(".zumen_cate_list_meisho"), d.select_one(".zumen_cate_list_view a")
        if not meisho or not view:
            continue
        m = PDF_ARG.search(view.get("onclick", "") or view.get("data-historyurl", ""))
        if not m:
            continue
        spans = meisho.find_all("span")
        model = " ".join(s.get_text(" ", strip=True) for s in spans if "br" in (s.get("class") or []))
        name = spans[0].get_text(" ", strip=True) if spans else ""
        text = meisho.get_text(" ", strip=True)
        rel = re.search(r"(\d{4})年(\d{1,2})月発売", text)
        shiryo = d.select_one(".zumen_cate_list_shiryo")
        target = unquote(m.group(1))
        out.append({"category": category, "name": name, "model": model, "text": text,
                    "release": f"{rel.group(1)}-{int(rel.group(2)):02d}" if rel else "",
                    "discontinued": "生産終了商品" in text, "doc": shiryo.get_text(" ", strip=True) if shiryo else "",
                    "url": urljoin(RESULT, target)})
    return out


def run(_: argparse.Namespace) -> None:
    c = PoliteClient(log_path=LOGS / f"{KEY}_requests.log")
    c.get(ENTRY + "notice.html")  # ご利用条件（同意は入口ページの文言による。ユーザーの包括承認あり）
    entry = decode(c.get(ENTRY))
    tops = {}
    for a in BeautifulSoup(entry, "lxml").find_all("a", href=re.compile(r"/scvb/a2A/zumenCategResult\?")):
        path = unquote(re.search(r"CATEGORY_KAISO=([^&]+)", a["href"]).group(1))
        label = a.get_text(" ", strip=True)
        if label or path not in tops:
            tops[path] = label
    tops = list(tops.items())
    items, pages, leaves = [], [], 0
    stack = [(p, l) for p, l in reversed(tops)]
    seen = set()
    while stack:
        path, label = stack.pop()
        if path in seen:
            continue
        seen.add(path)
        resp = c.get(RESULT, params=params_for(path))
        raw = decode(resp)
        soup = BeautifulSoup(raw, "lxml")
        depth = path.count("/")
        children = []
        for _, cpath, _, clabel in KAISO.findall(htmllib.unescape(raw)):
            if cpath.startswith(path + "/") and cpath.count("/") == depth + 1:
                children.append((cpath, f"{label}／{re.sub(r'\s*[(（]\d+件[)）]\s*$', '', clabel.strip())}"))
        rows = parse_rows(soup, label)
        form = soup.find("form", {"name": "listForm"})
        total_pages = 1
        if form:
            tp = form.find("input", {"name": "TOTALPAGENUM"})
            total_pages = int(tp["value"]) if tp and tp.get("value", "").isdigit() else 1
            base = [(i["name"], i.get("value", "")) for i in form.find_all("input")
                    if i.get("name") and i["name"] not in ("START_CNT", "USER_AGENT")]
            for page in range(2, total_pages + 1):
                more = BeautifulSoup(decode(c.get(RESULT, params=base + [("START_CNT", str((page - 1) * 20 + 1))])), "lxml")
                rows += parse_rows(more, label)
        if rows:
            leaves += 1
        items += rows
        pages.append({"path": path, "label": label, "status": resp.status_code, "children": len(children),
                      "pages": total_pages, "rows": len(rows), "fetched_at": now()})
        print(f"  {label}: children {len(children)}, rows {len(rows)} (total {len(items)})", flush=True)
        stack += list(reversed(children))
    rows_out, anomalies = [], []
    for it in {(i["url"], i["model"], i["doc"]): i for i in items}.values():
        # 緑字（span.br）は品番のこともあれば、発売年月・補足説明のこともある。
        # 品番らしい語だけで構成されるときは品番ごとの行、そうでなければ名称（＋補足）でシリーズ単位の1行。
        sub = re.sub(r"\d{4}年\d{1,2}月発売|生産終了商品", " ", it["model"]).strip()
        parts = [unicodedata.normalize("NFKC", p).strip() for p in re.split(r"[・／\s]+", sub) if p.strip()]
        if parts and all(MODEL_LIKE.fullmatch(p) for p in parts):
            entries = [(p, re.sub(r"[\s\-]", "", p.replace("○", "")).upper(), "hinban") for p in parts]
        else:
            series = re.sub(r"\s+", " ", f"{it['name']} {sub}").strip()
            entries = [(series, re.sub(r"\s+", "", unicodedata.normalize("NFKC", series)), "series")]
        for raw, norm, level in entries:
            rows_out.append({
                "maker": MAKER, "domain": DOMAIN, "product_category": it["category"], "model_raw": raw,
                "model_normalized": norm, "title": f"{it['doc']}（{it['name']}）",
                "url": it["url"], "url_type": "pdf" if it["url"].lower().endswith(".pdf") else "html",
                "source_method": "search_category", "first_seen": "", "http_status": "", "checked_at": "",
                "model_unconfirmed": "0" if raw else "1", "discontinued": "1" if it["discontinued"] else "0",
            })
            if level == "series":
                anomalies.append({"type": "series_level", "model": raw, "detail": it["doc"], "url": it["url"]})
    stats: Counter = Counter()
    statuses = check_urls(c, [r["url"] for r in rows_out], stats)
    for r in rows_out:
        r["http_status"], r["checked_at"] = statuses[r["url"]]
    url_models = defaultdict(set)
    for r in rows_out:
        url_models[r["url"]].add(r["model_raw"])
    anomalies += [{"type": "shared_url", "model": " ".join(sorted(ms)[:20]), "detail": len(ms), "url": u}
                  for u, ms in url_models.items() if len(ms) > 1]
    write_jsonl(RAW / f"{KEY}_pages.jsonl", [{"pages": pages, "items": items}])
    write_rows(RAW / f"{KEY}_manuals.csv", rows_out)
    write_anomalies(RAW / f"{KEY}_anomalies.csv", anomalies)
    summary = {"category_pages": len(pages), "leaf_pages_with_rows": leaves, "items": len(items), "rows": len(rows_out),
               "unique_urls": len(url_models), "models": len({r["model_raw"] for r in rows_out}),
               "current_rows": sum(r["discontinued"] == "0" for r in rows_out), "http": Counter(r["http_status"] for r in rows_out),
               "per_doc": Counter(i["doc"] for i in items).most_common(20),
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

"""検索ページをヘッドレスで開き、XHR/fetch を記録する調査用ツール。

    python -m collector.xhr_probe <url> <許可ホストの接尾辞,...> [クリックするテキスト ...]

- robots.txt で不可のリクエスト、画像・フォント・動画・CSSは送らない。
- ホストごとに送信開始を1秒以上あける。
"""
from __future__ import annotations

import json
import sys
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from collector.polite import USER_AGENT, PoliteClient

SKIP = {"image", "font", "media", "stylesheet"}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    url, hosts = sys.argv[1], tuple(h.strip().lower() for h in sys.argv[2].split(","))
    clicks = sys.argv[3:]
    client = PoliteClient()
    last: dict[str, float] = {}
    records: list[dict] = []

    def handler(route, request):
        target = request.url
        host = urlsplit(target).netloc.lower()
        if request.resource_type in SKIP or not target.startswith("http") or not host.endswith(hosts):
            return route.abort()
        if not client.can_fetch(target):
            print("ROBOTS-BLOCK", target)
            return route.abort()
        wait = 1.05 - (time.monotonic() - last.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        last[host] = time.monotonic()
        route.continue_()

    def on_response(resp):
        if resp.request.resource_type not in ("xhr", "fetch"):
            return
        try:
            body = resp.text()
        except Exception as exc:  # noqa: BLE001
            body = f"<{exc}>"
        records.append({
            "method": resp.request.method, "status": resp.status, "url": resp.url,
            "type": resp.headers.get("content-type", ""), "post": resp.request.post_data,
            "body": body[:3000],
        })

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=USER_AGENT, locale="ja-JP", service_workers="block")
        page = ctx.new_page()
        page.route("**/*", handler)
        page.on("response", on_response)
        page.goto(url, wait_until="load", timeout=180000)
        page.wait_for_timeout(6000)
        for text in clicks:
            page.get_by_text(text, exact=False).first.click()
            page.wait_for_timeout(6000)
        print("FINAL", page.url, page.title())
        print("BODY", page.inner_text("body")[:2500].replace("\n", " / "))
        anchors = page.eval_on_selector_all("a[href]", "els=>els.map(e=>[e.href,(e.innerText||'').trim().slice(0,60)])")
        print("ANCHORS", len(anchors))
        for href, text in anchors[:400]:
            print("A", href, "|", text)
        browser.close()
    for r in records:
        print("XHR", json.dumps({k: v for k, v in r.items() if k != "body"}, ensure_ascii=False))
        print("   ", r["body"][:1500].replace("\n", " "))


if __name__ == "__main__":
    main()

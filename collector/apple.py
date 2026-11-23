"""Collect Japanese hardware documentation links from Apple's public docs catalog.

The catalog supplies the product-to-document relationship. Never infer it from a
PDF filename. Software downloads and technical specifications are excluded.
PDF bodies are never downloaded. Run with ``python -m collector.apple``.
"""
from __future__ import annotations

import json
import csv
import random
import re
import time
import unicodedata
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from collector.common import LOGS, RAW, check_urls, now, write_rows
from collector.polite import PoliteClient

ROOT = 'https://support.apple.com/ja-jp/docs'
CATEGORIES = {'mac', 'ipad', 'iphone', 'watch', 'vision', 'airpods', 'home',
              'ipod', 'displays', 'accessories'}
MAX_PAGES = 1600
MAX_SECONDS = 2400


def parse_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    h = soup.select_one('h1.docs-headline')
    model = h.get_text(' ', strip=True) if h else ''
    links = {}
    for a in soup.select('a[href]'):
        target = urljoin(url, a['href']).split('#')[0].split('?')[0].rstrip('/')
        p = urlsplit(target)
        parts = p.path.strip('/').split('/')
        if p.netloc == 'support.apple.com' and len(parts) >= 3 and parts[:2] == ['ja-jp', 'docs'] and parts[2] in CATEGORIES:
            links[target] = a.get_text(' ', strip=True)
    documents = []
    for block in soup.select('.contentType-wrapper > div'):
        heading = block.select_one('h2')
        if not heading or heading.get_text(strip=True) not in ('ドキュメント', 'マニュアル', 'ユーザガイド'):
            continue
        for a in block.select('a.docs-link[href]'):
            target = urljoin(url, a['href'])
            if urlsplit(target).scheme == 'https' and urlsplit(target).netloc in ('support.apple.com', 'cdsassets.apple.com'):
                documents.append({'title': a.get_text(' ', strip=True), 'url': target})
    return {'url': url, 'model': model, 'links': links, 'documents': documents}


def run():
    RAW.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    cache = RAW / 'apple_pages.jsonl'
    previous = [json.loads(x) for x in cache.read_text(encoding='utf-8').splitlines()] if cache.exists() else []
    pages = {p['url']: p for p in previous if p.get('status') == 200}
    queue = deque([ROOT] + [u for p in previous for u in p.get('links', {})])
    seen = set()
    c = PoliteClient(LOGS / 'apple_requests.log', timeout=20, session_per_thread=True)
    start = time.monotonic()
    failures = []
    def fetch_page(u):
        if u in pages:
            return pages[u], False
        try:
            r = c.get(u)
            p = parse_page(r.text, u) if r.status_code == 200 else {'url': u, 'links': {}}
            p.update(status=r.status_code, fetched_at=now())
        except Exception as exc:
            p = {'url': u, 'status': type(exc).__name__, 'links': {}, 'error': str(exc)}
        return p, True
    with cache.open('a', encoding='utf-8') as out, ThreadPoolExecutor(max_workers=4) as pool:
        while queue and len(seen) < MAX_PAGES and time.monotonic() - start < MAX_SECONDS:
            batch = []
            while queue and len(batch) < 20 and len(seen) < MAX_PAGES:
                u = queue.popleft()
                if u not in seen:
                    seen.add(u); batch.append(u)
            for p, fresh in pool.map(fetch_page, batch):
                if fresh:
                    out.write(json.dumps(p, ensure_ascii=False) + '\n'); out.flush()
                    if p['status'] == 200:
                        pages[p['url']] = p
                    else:
                        failures.append(p)
                queue.extend(p.get('links', {}))
            if batch:
                print(json.dumps({'visited': len(seen), 'documents': sum(len(x.get('documents', [])) for x in pages.values())}), flush=True)
    rows = []
    for u, p in pages.items():
        parts = urlsplit(u).path.strip('/').split('/')
        if len(parts) < 4:
            continue
        model = p.get('model', '')
        # Family-level catalog records must not masquerade as a specific model.
        generic = model.casefold() in CATEGORIES or not model or parts[-1].startswith('pl')
        for doc in p.get('documents', []):
            rows.append(dict(maker='Apple', domain='通信', product_category=parts[2],
                model_raw='' if generic else model,
                model_normalized='' if generic else re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', model)).strip().upper(),
                title=doc['title'], url=doc['url'],
                url_type='pdf' if urlsplit(doc['url']).path.lower().endswith('.pdf') else 'html',
                source_method='crawl', first_seen='', http_status='', checked_at='',
                model_unconfirmed='1' if generic else '0', discontinued=''))
    rows = list({(r['model_raw'], r['url']): r for r in rows}.values())
    stats = Counter()
    sample = random.Random(20261123).sample(rows, min(50, len(rows)))
    print(json.dumps({'phase': 'head_sample', 'rows': len(rows), 'sample_rows': len(sample)}), flush=True)
    statuses = check_urls(c, [r['url'] for r in sample], stats, workers=2)
    for r in rows:
        r['http_status'], r['checked_at'] = statuses.get(r['url'], ('', ''))
    rows.sort(key=lambda r: (r['product_category'], r['model_raw'], r['url'], r['title']))
    write_rows(RAW / 'apple_manuals.csv', rows)
    with (RAW / 'apple_head_sample.csv').open('w', encoding='utf-8', newline='') as out:
        w = csv.DictWriter(out, ['model_raw', 'url', 'http_status', 'checked_at', 'pdf_body_model_match'])
        w.writeheader()
        w.writerows({k: '' if k == 'pdf_body_model_match' else r[k] for k in w.fieldnames} for r in sample)
    summary = dict(rows=len(rows), models=len({r['model_raw'] for r in rows if r['model_raw']}),
        unique_urls=len({r['url'] for r in rows}), pages=len(pages), failures=failures,
        sample_rows=len(sample), head_checked_unique_urls=len(statuses),
        stopped_by_limit=bool(set(queue)-seen), remaining_queue=len(set(queue) - seen),
        http=Counter(r['http_status'] for r in rows), categories=Counter(r['product_category'] for r in rows),
        max_pages=MAX_PAGES, max_seconds=MAX_SECONDS, completed_at=now(), **stats)
    (RAW / 'apple_build_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    run()

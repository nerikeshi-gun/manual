"""KENWOOD's Japanese vehicle manuals from the official JVCKENWOOD catalog.

Run catalog, fetch, build separately with ``python -m collector.kenwood <phase>``.
Keep original model spelling and the official catalog-to-download relationship.
No PDF bodies are fetched; files are checked with HEAD only (Range on rejection).
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
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from collector.common import LOGS, RAW, check_urls, load_jsonl, now, write_jsonl, write_rows
from collector.polite import PoliteClient

SITE = 'https://manuals.jvckenwood.com'
USER_SUPPLIED_PDF = SITE + '/download/files/B5A-2591-10.pdf'
CATEGORIES = {'CA': 'カーオーディオ', 'CN': 'カーナビ＆AV', 'CE': 'ドライブレコーダー＆カー用品システムアップ'}
MAX_LISTINGS, MAX_MODELS, MAX_SECONDS = 300, 2500, 3600


def client():
    LOGS.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    return PoliteClient(LOGS / 'kenwood_requests.log', timeout=20, session_per_thread=True)


def canonical_category(url):
    p = urlsplit(url)
    q = parse_qs(p.query)
    ca1 = q.get('CA1', [''])[0]
    if p.netloc != 'manuals.jvckenwood.com' or p.path != '/category.php' or ca1 not in CATEGORIES:
        return None
    params = {'BR': 'K', 'CA1': ca1}
    if q.get('CA2'):
        params['CA2'] = q['CA2'][0]
    page = int(q.get('PAGE', ['1'])[0])
    if page > 1:
        params['PAGE'] = str(page)
    params['ORD'] = 'RYD'
    return SITE + '/category.php?' + urlencode(params)


def parse_listing(html, url):
    soup = BeautifulSoup(html, 'lxml')
    categories, models = set(), []
    ca1 = parse_qs(urlsplit(url).query)['CA1'][0]
    for a in soup.select('a[href]'):
        target = urljoin(url, a['href'])
        category = canonical_category(target)
        if category:
            categories.add(category)
        p = urlsplit(target)
        # Some official model names contain a slash (DPX-055MD/S, E212/S).
        # Their download-page paths preserve it, so do not assume one segment.
        if p.netloc != 'manuals.jvckenwood.com' or not re.match(r'^/download/(?!files/).+_JA_JAJP_[A-Fa-f0-9]+/?$', p.path):
            continue
        li = a.find_parent('li')
        texts = [x.get_text(' ', strip=True) for x in li.select('p')] if li else []
        # Do not admit JVC or Victor documents when shared navigation loses BR.
        if 'KENWOOD' not in texts:
            continue
        models.append({'model_raw': a.get_text(' ', strip=True), 'url': target,
                       'category': CATEGORIES[ca1], 'listing_url': url,
                       'catalog_labels': texts})
    count = re.search(r'件数\s*([\d,]+)件', soup.get_text(' ', strip=True))
    return {'url': url, 'links': sorted(categories), 'models': models,
            'expected_count': int(count[1].replace(',', '')) if count else None}


def catalog():
    c = client()
    path = RAW / 'kenwood_catalog.jsonl'
    cached = {x['url']: x for x in load_jsonl(path) if x.get('status') == 200}
    queue = deque(canonical_category(SITE + '/category.php?CA1=' + ca) for ca in CATEGORIES)
    seen = set()
    start = time.monotonic()
    records, failures = [], []
    with path.open('a', encoding='utf-8') as out:
        while queue and len(seen) < MAX_LISTINGS and time.monotonic() - start < MAX_SECONDS:
            u = queue.popleft()
            if u in seen:
                continue
            seen.add(u)
            p = cached.get(u)
            if not p:
                try:
                    r = c.get(u)
                    p = parse_listing(r.text, u) if r.status_code == 200 else {'url': u, 'links': [], 'models': []}
                    p.update(status=r.status_code, fetched_at=now())
                except Exception as exc:
                    p = {'url': u, 'status': type(exc).__name__, 'links': [], 'models': [], 'error': str(exc)}
                out.write(json.dumps(p, ensure_ascii=False) + '\n')
                out.flush()
            records.append(p)
            queue.extend(p['links'])
            if p['status'] != 200:
                failures.append(p)
            if len(seen) % 10 == 0:
                print(json.dumps({'listing_pages': len(seen), 'model_links': sum(len(x['models']) for x in records)}), flush=True)
    models = {(m['model_raw'], m['url']): m for p in records for m in p['models']}
    write_jsonl(RAW / 'kenwood_models.jsonl', sorted(models.values(), key=lambda m: (m['category'], m['model_raw'], m['url'])))
    summary = {'listing_pages': len(seen), 'models': len(models), 'failures': failures,
               'remaining_queue': len(set(queue) - seen), 'stopped_by_limit': bool(set(queue) - seen),
               'scope': CATEGORIES, 'max_listings': MAX_LISTINGS, 'max_models': MAX_MODELS, 'max_seconds': MAX_SECONDS,
               'completed_at': now()}
    (RAW / 'kenwood_catalog_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def parse_detail(html, url):
    soup = BeautifulSoup(html, 'lxml')
    heading = soup.find('h2')
    documents = []
    for a in soup.select('.box a[href]'):
        target = urljoin(url, a['href'])
        p = urlsplit(target)
        label = a.get_text(' ', strip=True)
        if p.scheme != 'https' or not p.netloc.endswith(('.jvckenwood.com', '.kenwood.com', '.kenwood.co.jp')):
            continue
        if '.pdf' not in p.path.lower() and not re.search(r'説明|マニュアル|ガイド|manual|guide|web', label, re.I):
            continue
        documents.append({'title': label, 'url': target,
                          'url_type': 'pdf' if '.pdf' in p.path.lower() or re.search(r'PDF', label, re.I) else 'html'})
    return {'url': url, 'page_model': heading.get_text(' ', strip=True) if heading else '', 'documents': documents}


def fetch():
    c = client()
    models = load_jsonl(RAW / 'kenwood_models.jsonl')
    urls = sorted({m['url'] for m in models})
    if len(urls) > MAX_MODELS:
        raise RuntimeError(f'{len(urls)} model pages exceeds predeclared {MAX_MODELS}; no model pages sent')
    path = RAW / 'kenwood_pages.jsonl'
    done = {p['url'] for p in load_jsonl(path) if p.get('status') == 200}
    todo = [u for u in urls if u not in done]
    start = time.monotonic()

    def one(u):
        if time.monotonic() - start > MAX_SECONDS:
            return {'url': u, 'status': 'time_limit', 'documents': []}
        try:
            r = c.get(u)
            p = parse_detail(r.text, u) if r.status_code == 200 else {'url': u, 'documents': []}
            return dict(p, status=r.status_code, fetched_at=now())
        except Exception as exc:
            return {'url': u, 'status': type(exc).__name__, 'documents': [], 'error': str(exc)}

    print(json.dumps({'phase': 'fetch', 'total': len(urls), 'remaining': len(todo)}), flush=True)
    with path.open('a', encoding='utf-8') as out, ThreadPoolExecutor(max_workers=3) as pool:
        for i, p in enumerate(pool.map(one, todo), 1):
            out.write(json.dumps(p, ensure_ascii=False) + '\n')
            out.flush()
            if i % 25 == 0:
                print(json.dumps({'fetched': i, 'remaining': len(todo) - i}), flush=True)


def normalize(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value)).upper()


def build():
    c = client()
    models = load_jsonl(RAW / 'kenwood_models.jsonl')
    pages = {p['url']: p for p in load_jsonl(RAW / 'kenwood_pages.jsonl')}
    supplements = {p['model_raw']: p for p in load_jsonl(RAW / 'kenwood_resolved_links.jsonl')}
    rows, anomalies, evidence = [], [], []
    supplemented_models = set()
    for m in models:
        p = pages.get(m['url'], {})
        if p.get('status') != 200 or not p.get('documents'):
            supplement = supplements.get(m['model_raw'])
            if not supplement or supplement.get('model_url') != m['url'] or supplement.get('matched_model') != m['model_raw']:
                anomalies.append(dict(m, reason='no_documents_or_fetch_failed', status=p.get('status')))
                continue
            if any(urlsplit(d['url']).netloc != 'manuals.jvckenwood.com' or not d['url'].startswith(SITE + '/download/files/') for d in supplement['documents']):
                raise ValueError('Supplement must point to an explicitly verified official PDF')
            p = dict(p, documents=supplement['documents'], verified_model=supplement['matched_model'],
                     verification_method=supplement['verification_method'])
            supplemented_models.add(m['model_raw'])
        if normalize(m['model_raw']) != normalize(p.get('verified_model', p.get('page_model', ''))):
            anomalies.append(dict(m, reason='catalog_detail_model_mismatch', page_model=p.get('page_model')))
            continue
        for d in p['documents']:
            title = re.sub(r'\s*\([\d.]+\s*[KMG]?B\s*/\s*(PDF|HTML)\)\s*$', '', d['title'], flags=re.I).strip()
            row = dict(maker='ケンウッド', domain='車載', product_category=m['category'],
                       model_raw=m['model_raw'], model_normalized=normalize(m['model_raw']),
                       title=title, url=d['url'], url_type=d['url_type'], source_method='crawl',
                       first_seen='', http_status='', checked_at='', model_unconfirmed='0', discontinued='')
            rows.append(row)
            evidence.append(dict(row, listing_url=m['listing_url'], model_url=m['url'],
                                 page_model=p.get('page_model', ''), model_page_status=p.get('status'),
                                 verification_method=p.get('verification_method', 'catalog_and_model_page_heading'),
                                 catalog_labels=m['catalog_labels']))
    rows = list({(r['model_raw'], r['url']): r for r in rows}.values())
    # The collection instructions call for a random 50-row verification sample.
    # Leave other HTTP statuses empty, rather than passing off the model-page
    # response as a PDF response. Shared URLs need only one HEAD request.
    sample = random.Random(20261123).sample(rows, min(50, len(rows)))
    print(json.dumps({'phase': 'head_sample', 'rows': len(rows), 'sample_rows': len(sample), 'urls': len({r['url'] for r in sample}), 'anomalies': len(anomalies)}), flush=True)
    stats = Counter()
    supplemental_urls = [d['url'] for s in supplements.values() for d in s['documents']]
    statuses = check_urls(c, [r['url'] for r in sample] + [USER_SUPPLIED_PDF] + supplemental_urls, stats, workers=3)
    for r in rows:
        r['http_status'], r['checked_at'] = statuses.get(r['url'], ('', ''))
    write_rows(RAW / 'kenwood_manuals.csv', sorted(rows, key=lambda r: (r['product_category'], r['model_raw'], r['url'])))
    write_jsonl(RAW / 'kenwood_evidence.jsonl', evidence)
    write_jsonl(RAW / 'kenwood_anomalies.jsonl', anomalies)
    with (RAW / 'kenwood_head_sample.csv').open('w', encoding='utf-8', newline='') as out:
        writer = csv.DictWriter(out, ['model_raw', 'url', 'http_status', 'checked_at', 'pdf_body_model_match'])
        writer.writeheader()
        writer.writerows({k: ('' if k == 'pdf_body_model_match' else r[k]) for k in writer.fieldnames} for r in sample)
    summary = dict(rows=len(rows), models=len({r['model_raw'] for r in rows}), unique_urls=len({r['url'] for r in rows}),
                   sample_rows=len(sample), head_checked_unique_urls=len(statuses),
                   user_supplied_pdf=USER_SUPPLIED_PDF,
                   http=Counter(r['http_status'] for r in rows), categories=Counter(r['product_category'] for r in rows),
                   anomalies=len(anomalies), catalog_models=len(models), completed_at=now(), **stats)
    summary['supplemented_models'] = sorted(supplemented_models)
    (RAW / 'kenwood_build_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['catalog', 'fetch', 'build'])
    args = parser.parse_args()
    globals()[args.phase]()

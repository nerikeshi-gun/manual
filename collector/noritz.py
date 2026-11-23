"""Record manual links explicitly published in Noritz's public FAQ.

The PDF host prohibits crawling. Record links from the permitted FAQ without
requesting those PDFs. This is a limited six-series batch, not the full catalog.
"""
import json
import re
import unicodedata
from collections import Counter
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from collector.common import RAW, LOGS, now, write_rows, write_jsonl, check_urls
from collector.polite import PoliteClient

URL = 'https://faq.noritz.co.jp/%E5%8F%96%E6%89%B1%E8%AA%AC%E6%98%8E%E6%9B%B8%E3%82%92%E8%A6%8B%E3%81%9F%E3%81%84-64ba5c5c1ec10c001ca546e7'

def run():
    c = PoliteClient(LOGS/'noritz_requests.log', timeout=20)
    r = c.get(URL);r.raise_for_status()
    soup = BeautifulSoup(r.content,'lxml')
    rows,evidence = [],[]
    for a in soup.select('a[href]'):
        label = a.get_text(' ',strip=True)
        p = urlsplit(a['href'])
        if not label.startswith('リモコン型式 ') or p.netloc!='www.n-techdocs.com' or not re.fullmatch(r'/products/\d+/documents/\d+/download',p.path):
            continue
        model = label.removeprefix('リモコン型式 ').strip()
        row = dict(maker='ノーリツ',domain='住設',product_category='給湯リモコン',model_raw=model,
            model_normalized=unicodedata.normalize('NFKC',model).replace(' ','').upper(),
            title='取扱説明書（'+model+'）',url=a['href'],url_type='pdf',source_method='crawl',
            first_seen='',http_status='',checked_at='',model_unconfirmed='0',discontinued='')
        rows.append(row);evidence.append(dict(row,source_url=URL,source_label=label,fetched_at=now()))
    rows = list({(r['model_raw'],r['url']):r for r in rows}.values())
    if not rows:
        raise ValueError('No matching explicit FAQ links; do not publish an empty success')
    stats = Counter()
    statuses = check_urls(c,[r['url']for r in rows],stats,workers=1)
    for row in rows:
        row['http_status'],row['checked_at'] = statuses[row['url']]
    write_rows(RAW/'noritz_manuals.csv',rows)
    write_jsonl(RAW/'noritz_evidence.jsonl',evidence)
    summary = dict(rows=len(rows),series=len(rows),unique_urls=len(statuses),
        scope='public FAQ explicitly linked remote-controller series only; full product catalog not collected',
        pdf_body_model_match='not_verified',completed_at=now(),**stats)
    (RAW/'noritz_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':run()

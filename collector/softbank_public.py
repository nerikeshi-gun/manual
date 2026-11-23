"""Initial batch from directly accessible official manual HTML pages.

Do not use the token-bearing list/search API or browser interaction that was
previously deferred. Seeds are explicit official pages found in public search.
"""
import json
import random
import re
import sys
import unicodedata
from collections import Counter
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup
from collector.common import RAW,LOGS,now,write_rows,write_jsonl,check_urls
from collector.polite import PoliteClient

SEEDS=[
 'https://www.softbank.jp/mobile/support/product/004z/download/',
 'https://www.softbank.jp/mobile/support/product/930ca/download/',
 'https://www.softbank.jp/mobile/support/manual/smartphone/s5/',
 'https://www.softbank.jp/mobile/support/manual/smartphone/anshin-family-sumaho/pdf/'
]

def run():
    c=PoliteClient(LOGS/'softbank_public_requests.log',timeout=20)
    rows,evidence,pages=[],[],[]
    for seed in SEEDS:
        r=c.get(seed,stream=True)
        if 'html'not in r.headers.get('Content-Type',''):
            r.close();raise ValueError('Expected HTML manual page; PDF body not read')
        s=BeautifulSoup(r.content,'lxml')
        h=s.find('h1');heading=h.get_text(' ',strip=True)if h else''
        title=s.title.get_text(' ',strip=True)if s.title else''
        model=re.split(r'\s*(?:取扱説明書|オンラインマニュアル)',heading or title)[0].strip()
        path=urlsplit(seed).path
        parts=path.strip('/').split('/')
        slug=parts[parts.index('product')+1]if 'product'in parts else parts[parts.index('smartphone')+1]
        docs=[]
        for a in s.select('a[href]'):
            u=urljoin(r.url,a['href']);p=urlsplit(u)
            if p.netloc=='www.softbank.jp'and p.path.lower().endswith('.pdf')and '/'+slug+'/'in p.path.lower():
                docs.append({'url':u,'title':a.get_text(' ',strip=True)or'取扱説明書','url_type':'pdf'})
        if 'オンラインマニュアル'in(title+heading)and not path.endswith('/pdf/')and model:
            docs.append({'url':r.url,'title':'オンラインマニュアル（取扱説明書）','url_type':'html'})
        pages.append({'url':seed,'status':r.status_code,'heading':heading,'title':title,'model_raw':model,'documents':docs,'fetched_at':now()})
        if r.status_code!=200:continue
        for d in docs:
            row=dict(maker='ソフトバンク',domain='通信',product_category='携帯端末',model_raw=model,
                model_normalized=unicodedata.normalize('NFKC',model).upper().replace(' ',''),title=d['title'],url=d['url'],url_type=d['url_type'],
                source_method='crawl',first_seen='',http_status='',checked_at='',model_unconfirmed='0'if model else'1',discontinued='')
            rows.append(row);evidence.append(dict(row,source_url=seed,source_heading=heading))
    rows=list({(r['model_raw'],r['url']):r for r in rows}.values())
    if not rows:raise ValueError('No manual URLs were found')
    sample=random.Random(20261123).sample(rows,min(50,len(rows)))
    statuses=check_urls(c,[r['url']for r in sample],Counter(),workers=2)
    for r in rows:r['http_status'],r['checked_at']=statuses.get(r['url'],('',''))
    write_rows(RAW/'softbank_public_manuals.csv',rows);write_rows(RAW/'softbank_public_head_sample.csv',sample)
    write_jsonl(RAW/'softbank_public_pages.jsonl',pages);write_jsonl(RAW/'softbank_public_evidence.jsonl',evidence)
    summary=dict(scope='four explicit official model-manual pages only, not full catalog',pages=len(pages),
        models=len({r['model_raw']for r in rows if r['model_raw']}),rows=len(rows),unique_urls=len({r['url']for r in rows}),
        sample_rows=len(sample),sample_http=dict(Counter(r['http_status']for r in sample)),search_api_used=False,
        completed_at=now(),model_pages_without_collected_links=[p['url']for p in pages if not p['documents']])
    (RAW/'softbank_public_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');run()

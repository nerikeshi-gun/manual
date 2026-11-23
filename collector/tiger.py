"""Collect Tiger manuals linked by the public Japanese product catalog.

The catalog's published JS calls /wp-json/api/v1/product with region=jpn.
Public TIGER FOREST manual landing pages need no membership or login.
Neither the disallowed search.tiger.jp/search nor member pages are visited.
"""
from __future__ import annotations
import json
import random
import re
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from collector.common import RAW, LOGS, load_jsonl, now, write_jsonl, write_rows, check_urls
from collector.polite import PoliteClient

API = 'https://www.tiger-corporation.com/wp-json/api/v1/product'
MAX_CATALOG_PAGES = 200
MAX_PRODUCTS = 2400

def html(c, url):
    r = c.get(url, stream=True)
    if 'html' not in r.headers.get('Content-Type', ''):
        r.close()
        raise ValueError('Not HTML; body was not read: '+url)
    text = r.text
    return r.status_code, r.url, BeautifulSoup(text, 'lxml')

def run():
    c = PoliteClient(LOGS/'tiger_requests.log', timeout=20, session_per_thread=True)
    RAW.mkdir(parents=True, exist_ok=True)
    products = {}
    catalog = []
    exhausted = False
    for page in range(1, MAX_CATALOG_PAGES+1):
        r = c.get(API, params={'region':'jpn', 'detailed':'true', 'paged':page})
        r.raise_for_status()
        items = r.json()
        if not isinstance(items, list):
            raise ValueError('Unexpected catalog response')
        entries = [{k:p.get(k) for k in ('ID','slug','product_name','url')} for p in items]
        catalog.append({'url':r.url, 'status':r.status_code, 'products':entries, 'fetched_at':now()})
        fresh = [p for p in entries if p['ID'] not in products]
        for p in fresh:
            products[p['ID']] = p
        if len(items)<12:
            exhausted = True
            break
        if not fresh:
            raise ValueError('Catalog repeated an entire page; pagination not proven')
    write_jsonl(RAW/'tiger_catalog.jsonl', catalog)
    if len(products)>MAX_PRODUCTS:
        raise ValueError('Product count exceeds predeclared limit')
    path = RAW/'tiger_pages.jsonl'
    cached = {p['product']['ID']:p for p in load_jsonl(path) if p.get('status')==200 and p.get('documents')}
    todo = [p for p in products.values() if p['ID'] not in cached]
    print(json.dumps({'products':len(products), 'remaining':len(todo), 'catalog_exhausted':exhausted}), flush=True)

    def one(product):
        rec = {'product':product, 'documents':[], 'manual_pages':[], 'fetched_at':now()}
        try:
            status, final, soup = html(c, product['url'])
            rec.update(status=status, product_url=final)
            if status!=200:
                return rec
            rec['product_heading'] = soup.title.get_text(' ', strip=True) if soup.title else ''
            def landing_links(ss,base):
                return sorted({urljoin(base,a['href']) for a in ss.select('a[href]')
                    if urlsplit(urljoin(base,a['href'])).netloc in ('www.tiger-forest.com','tiger-forest.com')
                    and '/manuals/' in urlsplit(urljoin(base,a['href'])).path
                    and not urlsplit(urljoin(base,a['href'])).path.endswith('/file')})
            targets = landing_links(soup,final)
            if not targets:
                jp = next((urljoin(final,a['href']) for a in soup.select('a[href]')
                    if a.get_text(strip=True)=='日本語' and '/ja/jpn/product/' in urljoin(final,a['href'])),None)
                if jp:
                    jst,jfinal,jsoup = html(c,jp)
                    rec['japanese_product_url']=jfinal
                    if jst==200:
                        soup,final=jsoup,jfinal
                        targets=landing_links(soup,final)
            rec['manual_landing_urls'] = targets
            for target in targets:
                st, landing, ms = html(c, target)
                title = ms.select_one('.tf-title--xl')
                label = title.get_text(' ', strip=True) if title else ''
                links = [{'url':urljoin(landing,a['href']), 'label':a.get_text(' ', strip=True)}
                         for a in ms.select('a[href]') if a.get_text(strip=True)=='日本語'
                         and '/manuals/' in urljoin(landing,a['href']) and urljoin(landing,a['href']).endswith('/file')]
                rec['manual_pages'].append({'url':target, 'final_url':landing, 'status':st, 'model_label':label, 'links':links})
                if st!=200:
                    continue
                raw_label = re.sub(r'\s*\(PDF\)\s*$', '', label, flags=re.I).strip()
                parts = [s.strip() for s in re.split('[,、，]', raw_label) if s.strip()]
                models = [p for p in parts if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 /().-]*', p)]
                if len(models)!=len(parts) or not models:
                    models = ['']
                for link in links:
                    for model in models:
                        rec['documents'].append({'model_raw':model, 'url':link['url'], 'title':'取扱説明書',
                            'landing_url':landing, 'model_label':raw_label, 'category':urlsplit(final).path.split('/product/')[-1].split('/')[0]})
            if not rec['documents']:
                for a in soup.select('a[href]'):
                    target=urljoin(final,a['href']);label=a.get_text(' ',strip=True)
                    host=urlsplit(target).netloc
                    if not(host.endswith('.tiger-forest.com')or host.endswith('.tiger-corporation.com')or host.endswith('.tiger.jp')):
                        continue
                    if not re.search(r'取扱説明書|instruction manual',label,re.I):
                        continue
                    if not(urlsplit(target).path.endswith('/file')or urlsplit(target).path.lower().endswith('.pdf')):
                        continue
                    rec['documents'].append({'model_raw':'','url':target,'title':label,'landing_url':final,
                        'model_label':product['product_name'],'category':urlsplit(final).path.split('/product/')[-1].split('/')[0]})
        except Exception as exc:
            rec.update(status=type(exc).__name__, error=str(exc))
        return rec

    with path.open('a', encoding='utf-8') as out, ThreadPoolExecutor(max_workers=3) as pool:
        for i,p in enumerate(pool.map(one,todo),1):
            out.write(json.dumps(p,ensure_ascii=False)+'\n');out.flush()
            cached[p['product']['ID']] = p
            if i%20==0:
                print(json.dumps({'fetched':i,'remaining':len(todo)-i}),flush=True)
    rows, evidence, gaps = [], [], []
    for product in products.values():
        p = cached.get(product['ID'], {})
        if not p.get('documents'):
            gaps.append({'product':product,'status':p.get('status'),'manual_pages':p.get('manual_pages',[]),'error':p.get('error','')})
        for d in p.get('documents',[]):
            explicit=d['model_raw']
            if not re.search(r'\d',explicit):
                candidates=re.findall(r'(?<![A-Z0-9])[A-Z]{2,6}-[A-Z0-9-]*\d[A-Z0-9-]*(?![A-Z0-9])',product.get('product_name',''))
                explicit=candidates[0]if len(set(candidates))==1 else ''
            row = dict(maker='タイガー',domain='家電',product_category=d['category'],model_raw=explicit,
                       model_normalized=unicodedata.normalize('NFKC',explicit).upper().replace(' ',''),
                       title=d['title'],url=d['url'],url_type='pdf',source_method='crawl',first_seen='',
                       http_status='',checked_at='',model_unconfirmed='0' if explicit else '1',discontinued='')
            rows.append(row)
            evidence.append(dict(row, product_url=p.get('product_url'),landing_url=d['landing_url'],model_label=d['model_label']))
    rows = list({(r['model_raw'],r['url']):r for r in rows}.values())
    sample = random.Random(20261123).sample(rows,min(50,len(rows)))
    statuses = check_urls(c,[r['url']for r in sample], Counter(),workers=2)
    for r in rows:
        r['http_status'],r['checked_at'] = statuses.get(r['url'],('',''))
    write_rows(RAW/'tiger_manuals.csv',sorted(rows,key=lambda r:(r['product_category'],r['model_raw'],r['url'])))
    write_jsonl(RAW/'tiger_evidence.jsonl',evidence)
    write_jsonl(RAW/'tiger_gaps.jsonl',gaps)
    write_rows(RAW/'tiger_head_sample.csv',sample)
    summary = {'catalog_products':len(products),'catalog_pages':len(catalog),'catalog_exhausted':exhausted,
               'scope':'default Japanese product catalog; discontinued-only catalog not yet enumerated',
               'rows':len(rows),'models':len({r['model_raw']for r in rows if r['model_raw']}),'unique_urls':len({r['url']for r in rows}),
               'products_without_collected_manual':len(gaps),'sample_rows':len(sample),'head_checked_unique_urls':len(statuses),
               'sample_http':dict(Counter(r['http_status']for r in sample)),
               'completed_at':now(),'max_catalog_pages':MAX_CATALOG_PAGES,'max_products':MAX_PRODUCTS}
    (RAW/'tiger_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    run()

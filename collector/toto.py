"""Bounded first batch from COM-ET's four publicly linked product-zone lists.

Collect each listed series search's first page, then up to 500 explicit manual
landing pages. Preserve pagination links for the following batch, not as done.
"""
import json
import random
import re
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin,urlsplit,parse_qs
from bs4 import BeautifulSoup
from collector.common import RAW,LOGS,load_jsonl,now,write_rows,write_jsonl,check_urls
from collector.polite import PoliteClient

SITE='https://www.com-et.com'
ZONES=('kitchen','bath','groom','toilet')
MAX_SEARCHES=180
MAX_MODELS=500

def soup_get(c,u):
    r=c.get(u);return r.status_code,BeautifulSoup(r.content,'lxml')

def run():
    c=PoliteClient(LOGS/'toto_requests.log',timeout=20,session_per_thread=True)
    seeds={}
    for zone in ZONES:
        u=f'{SITE}/jp/page/{zone}/';status,s=soup_get(c,u)
        if status!=200:raise ValueError(f'Zone failed: {u}: {status}')
        for a in s.select('a[href]'):
            target=urljoin(u,a['href'])
            if a.get_text(strip=True)=='説明書'and urlsplit(target).path.startswith('/jp/item_search/'):
                seeds.setdefault(target,{'url':target,'zone':zone,'source_url':u})
    if len(seeds)>MAX_SEARCHES:raise ValueError('Search seeds exceed predeclared bound')
    listing_path=RAW/'toto_listings.jsonl'
    listings={p['url']:p for p in load_jsonl(listing_path)if p.get('status')==200}
    def listing(seed):
        try:
            status,s=soup_get(c,seed['url']);models=[]
            for a in s.select('a[href]'):
                target=urljoin(seed['url'],a['href']);p=urlsplit(target)
                if p.netloc!='www.com-et.com'or p.path!='/jp/item_view_manual/':continue
                model=parse_qs(p.query).get('hinban',[''])[0]
                if model:models.append({'model_raw':model,'url':target,'zone':seed['zone'],'listing_url':seed['url']})
            pagination=sorted({urljoin(seed['url'],a['href'])for a in s.select('a[href]')if '/jp/item_search/'in a['href']and re.search(r'page[=/]|pageno[=/]',a['href'],re.I)})
            count=re.search(r'検索件数[：:]\s*([^件]+)件',s.get_text(' ',strip=True))
            return dict(seed,status=status,models=models,pagination_not_collected=pagination,
                        displayed_count=count[1]if count else '',fetched_at=now())
        except Exception as e:return dict(seed,status=type(e).__name__,models=[],error=str(e))
    todo=[p for u,p in seeds.items()if u not in listings]
    print(json.dumps({'searches':len(seeds),'remaining':len(todo)}),flush=True)
    with listing_path.open('a',encoding='utf-8')as out,ThreadPoolExecutor(max_workers=8)as pool:
        for i,p in enumerate(pool.map(listing,todo),1):
            out.write(json.dumps(p,ensure_ascii=False)+'\n');out.flush();listings[p['url']]=p
            if i%20==0:print(json.dumps({'searches_fetched':i,'remaining':len(todo)-i}),flush=True)
    # Round robin across zones before the detail-page quota, preserving a queue.
    by_zone={z:{}for z in ZONES}
    for u in seeds:
        for m in listings.get(u,{}).get('models',[]):by_zone[m['zone']].setdefault(m['model_raw'],m)
    ordered=[]
    buckets={z:list(v.values())for z,v in by_zone.items()}
    for i in range(max((len(v)for v in buckets.values()),default=0)):
        for z in ZONES:
            if i<len(buckets[z]):ordered.append(buckets[z][i])
    selected=list({m['model_raw']:m for m in ordered}.values())
    write_jsonl(RAW/'toto_pending_models.jsonl',selected[MAX_MODELS:])
    selected=selected[:MAX_MODELS]
    write_jsonl(RAW/'toto_models.jsonl',selected)
    path=RAW/'toto_pages.jsonl';pages={p['model_raw']:p for p in load_jsonl(path)if p.get('status')==200}
    def detail(m):
        try:
            status,s=soup_get(c,m['url']);docs=[]
            model_text=''
            for dt in s.select('dt'):
                if dt.get_text(strip=True)=='品番':
                    dd=dt.find_next_sibling('dd')
                    if dd:model_text=dd.get_text(' ',strip=True).lstrip('：: ').strip();break
            for a in s.select('a[href]'):
                u=urljoin(m['url'],a['href']);p=urlsplit(u)
                if p.netloc!='search.toto.jp'or not p.path.startswith('/tr/')or not p.path.lower().endswith('.pdf'):continue
                tr=a.find_parent('tr');cells=tr.find_all(['td','th'],recursive=False)if tr else []
                title=cells[1].get_text(' ',strip=True)if len(cells)>1 else ''
                if title:docs.append({'url':u,'title':title})
            return dict(m,status=status,page_model=model_text,documents=docs,fetched_at=now())
        except Exception as e:return dict(m,status=type(e).__name__,documents=[],error=str(e))
    todo=[m for m in selected if m['model_raw']not in pages]
    print(json.dumps({'model_pages':len(selected),'remaining':len(todo)}),flush=True)
    with path.open('a',encoding='utf-8')as out,ThreadPoolExecutor(max_workers=8)as pool:
        for i,p in enumerate(pool.map(detail,todo),1):
            out.write(json.dumps(p,ensure_ascii=False)+'\n');out.flush();pages[p['model_raw']]=p
            if i%25==0:print(json.dumps({'models_fetched':i,'remaining':len(todo)-i}),flush=True)
    rows,evidence,gaps=[],[],[]
    # COM-ET explicitly defines ◆ as its recommendation badge, not a model
    # character. Preserve the displayed heading in evidence, ignoring this
    # decoration only when matching it against the query's product number.
    norm=lambda v:unicodedata.normalize('NFKC',v).upper().replace(' ','').removeprefix('◆')
    for m in selected:
        p=pages.get(m['model_raw'],{})
        if p.get('status')!=200 or not p.get('documents'):
            gaps.append(dict(m,status=p.get('status'),page_model=p.get('page_model'),reason='missing_docs_or_model_mismatch'));continue
        matched=norm(m['model_raw'])==norm(p.get('page_model',''))
        if not matched:
            gaps.append(dict(m,status=p.get('status'),page_model=p.get('page_model'),reason='model_mismatch_manual_urls_retained_without_model'))
        for d in p['documents']:
            row=dict(maker='TOTO',domain='住設',product_category=m['zone'],model_raw=m['model_raw']if matched else'',model_normalized=norm(m['model_raw'])if matched else'',
                title=d['title'],url=d['url'],url_type='pdf',source_method='crawl',first_seen='',http_status='',checked_at='',model_unconfirmed='0'if matched else'1',discontinued='')
            rows.append(row);evidence.append(dict(row,listing_url=m['listing_url'],model_url=m['url'],requested_model=m['model_raw'],page_model=p['page_model']))
    rows=list({(r['model_raw'],r['url']):r for r in rows}.values())
    sample=random.Random(20261123).sample(rows,min(50,len(rows)))
    statuses=check_urls(c,[r['url']for r in sample],Counter(),workers=2)
    for r in rows:r['http_status'],r['checked_at']=statuses.get(r['url'],('',''))
    write_rows(RAW/'toto_manuals.csv',rows);write_rows(RAW/'toto_head_sample.csv',sample)
    write_jsonl(RAW/'toto_evidence.jsonl',evidence);write_jsonl(RAW/'toto_gaps.jsonl',gaps)
    summary=dict(scope='four public product zones, series-search first pages, up to 500 model pages; not full catalog',
        searches=len(seeds),discovered_models=len(ordered),selected_model_pages=len(selected),models=len({r['model_raw']for r in rows if r['model_raw']}),
        model_unconfirmed_rows=sum(r['model_unconfirmed']=='1'for r in rows),
        rows=len(rows),unique_urls=len({r['url']for r in rows}),gaps=len(gaps),sample_rows=len(sample),sample_http=dict(Counter(r['http_status']for r in sample)),
        max_searches=MAX_SEARCHES,max_models=MAX_MODELS,completed_at=now())
    (RAW/'toto_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');run()

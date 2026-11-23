"""Traverse Epson/Brother public manual catalogs, including hidden old models.

No current-only filtering, date cut-off, model quota, private endpoints or PDF
bodies. Cache source-page metadata for resumable collection and audit gaps.
"""
import json
import random
import re
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin,urlsplit,parse_qs,urlencode
from bs4 import BeautifulSoup
from collector.common import RAW,LOGS,now,load_jsonl,write_jsonl,write_rows,check_urls
from collector.polite import PoliteClient

CONFIG={
 'epson':dict(maker='エプソン',root='https://www.epson.jp/support/manual/',host='www.epson.jp',doc_hosts={'www.epson.jp','www2.epson.jp','download4.epson.biz','download.epson-biz.com','support.epson.net'}),
 'brother':dict(maker='ブラザー',root='https://support.brother.co.jp/j/b/productsearch.aspx?c=jp&lang=ja&content=ml',host='support.brother.co.jp',doc_hosts={'support.brother.co.jp','support.brother.com','download.brother.com'})}

def run(key):
    cfg=CONFIG[key];c=PoliteClient(LOGS/f'{key}_requests.log',timeout=25,session_per_thread=True)
    listing_path=RAW/f'{key}_listings.jsonl';listings={p['url']:p for p in load_jsonl(listing_path)if p.get('status')==200}
    models={};todo={cfg['root']:dict(url=cfg['root'],kind='root',source_url='')};seen=set()
    def fetch(seed):
        try:
            r=c.get(seed['url'],stream=True);r.raise_for_status()
            if 'html'not in r.headers.get('content-type','').lower():r.close();raise ValueError('Refusing non-HTML body')
            s=BeautifulSoup(r.content,'lxml');r.close();return r,s
        except Exception:raise
    while todo:
        batch=[x for u,x in todo.items()if u not in seen];todo={}
        if not batch:break
        def listing(seed):
            if seed['url']in listings:return listings[seed['url']]
            try:
                r,s=fetch(seed);links=[];found=[]
                for a in s.select('a[href]'):
                    u=urljoin(r.url,a['href']);p=urlsplit(u);label=a.get_text(' ',strip=True)
                    if p.netloc!=cfg['host']:continue
                    if key=='epson':
                        if re.fullmatch(r'/support/used/ks/\d+\.htm',p.path):links.append(dict(url=u,kind='category',category=label,source_url=r.url))
                        elif p.path.startswith('/support/portal/used/')and p.path.endswith('.htm')and label:
                            found.append(dict(url=u.split('#')[0],model_raw=label,category=seed.get('category',''),source_url=r.url))
                    else:
                        q=parse_qs(p.query)
                        if p.path=='/j/b/productseries.aspx':links.append(dict(url=u,kind='category',category=label,source_url=r.url))
                        elif p.path=='/j/b/manualtop.aspx'and q.get('prod'):
                            found.append(dict(url=u,product_id=q['prod'][0],model_raw=label,category=seed.get('category',''),source_url=r.url))
                if key=='brother' and seed['kind']=='category':
                    q=parse_qs(urlsplit(seed['url']).query)
                    for a in s.select('a[href^="#Series-"]'):
                        series=a['href'].split('-')[1]
                        params=dict(series=series,c='jp',lang='ja',pcatid=q['pcatid'][0],content='ml')
                        u='https://support.brother.co.jp/j/b/productsearchajax.aspx?'+urlencode(params)
                        links.append(dict(url=u,kind='series_ajax',category=seed.get('category',''),source_url=r.url))
                return dict(seed,status=r.status_code,links=links,models=found,fetched_at=now())
            except Exception as e:return dict(seed,status=type(e).__name__,links=[],models=[],error=str(e),fetched_at=now())
        with ThreadPoolExecutor(max_workers=6)as pool,listing_path.open('a',encoding='utf-8')as out:
            for p in pool.map(listing,batch):
                seen.add(p['url']);listings[p['url']]=p;out.write(json.dumps(p,ensure_ascii=False)+'\n');out.flush()
                for m in p.get('models',[]):models.setdefault(m['url'],m)
                for x in p.get('links',[]):
                    if x['url']not in seen:todo[x['url']]=x
        print(json.dumps(dict(maker=key,catalog_pages=len(seen),pending_catalog_pages=len(todo),models=len(models))),flush=True)
    selected=list(models.values());write_jsonl(RAW/f'{key}_models.jsonl',selected)
    path=RAW/f'{key}_pages.jsonl';pages={p['url']:p for p in load_jsonl(path)if p.get('status')==200}
    remaining=[m for m in selected if m['url']not in pages]
    print(json.dumps(dict(maker=key,model_pages=len(selected),remaining=len(remaining))),flush=True)
    def detail(m):
        try:
            r,s=fetch(m);body=s.get_text(' ',strip=True);model=m['model_raw']
            if key=='brother':
                lead=s.select_one('p.leadtxt')
                if lead and lead.get_text(strip=True):model=lead.get_text(' ',strip=True)
            docs=[]
            for a in s.select('a[href]'):
                u=urljoin(r.url,a['href']);p=urlsplit(u)
                if p.netloc not in cfg['doc_hosts']:continue
                is_pdf=p.path.lower().endswith('.pdf')
                is_html=(any(t in p.path.lower()for t in ['/htmldoc/','/sec_pubs/','/manual/','/j/s/support/html/'])and p.path.lower().endswith(('.html','.htm','/')))
                if not(is_pdf or is_html):continue
                title=a.get_text(' ',strip=True)
                if key=='brother':
                    tr=a.find_parent('tr');em=tr.select_one('td em')if tr else None
                    if em:title=em.get_text(' ',strip=True)
                if not title or any(t in title for t in ['カタログ','ライセンス','個人情報']):continue
                docs.append(dict(url=u,title=title,url_type='pdf'if is_pdf else'html'))
            norm=lambda v:unicodedata.normalize('NFKC',v).upper().replace(' ','')
            return dict(m,status=r.status_code,page_model=model,model_mentioned=norm(model)in norm(body),documents=docs,
                discontinued_explicit=bool(re.search(r'(?:販売|生産)(?:を)?終了',body)),fetched_at=now())
        except Exception as e:return dict(m,status=type(e).__name__,documents=[],error=str(e),fetched_at=now())
    with ThreadPoolExecutor(max_workers=8)as pool,path.open('a',encoding='utf-8')as out:
        for i,p in enumerate(pool.map(detail,remaining),1):
            pages[p['url']]=p;out.write(json.dumps(p,ensure_ascii=False)+'\n');out.flush()
            if i%50==0:print(json.dumps(dict(maker=key,fetched=i,total=len(remaining))),flush=True)
    rows=[];evidence=[];gaps=[]
    for m in selected:
        p=pages.get(m['url'],{})
        if p.get('status')!=200 or not p.get('documents'):gaps.append(p or m)
        for d in p.get('documents',[]):
            model=p['page_model'];row=dict(maker=cfg['maker'],domain='家電',product_category=m['category']or'電子機器',model_raw=model,
                model_normalized=unicodedata.normalize('NFKC',model).upper(),title=d['title'],url=d['url'],url_type=d['url_type'],source_method='api'if key=='brother'else'crawl',
                first_seen='',http_status='',checked_at='',model_unconfirmed='0'if model else'1',discontinued='')
            # A generic sales-ended notice elsewhere on the source page is
            # insufficient to classify this exact product's production state.
            rows.append(row);evidence.append(dict(row,source_url=m['url'],catalog_url=m['source_url'],model_mentioned=p['model_mentioned'],
                source_body_discontinued_marker=p['discontinued_explicit'],fetched_at=p['fetched_at']))
    rows=list({(r['model_raw'],r['url']):r for r in rows}.values())
    sample=random.Random(20261123).sample(rows,min(50,len(rows)));stats=Counter();statuses=check_urls(c,[r['url']for r in sample],stats,workers=3)
    for row in rows:
        if row['url']in statuses:row['http_status'],row['checked_at']=statuses[row['url']]
    write_rows(RAW/f'{key}_manuals.csv',rows);write_rows(RAW/f'{key}_head_sample.csv',sample)
    write_jsonl(RAW/f'{key}_evidence.jsonl',evidence);write_jsonl(RAW/f'{key}_gaps.jsonl',gaps)
    summary=dict(catalog_pages=len(seen),catalog_failures=[u for u in seen if listings[u].get('status')!=200],model_pages=len(selected),
        failed_model_pages=sum(pages.get(m['url'],{}).get('status')!=200 for m in selected),model_pages_without_documents=len(gaps),
        rows=len(rows),named_models=len({r['model_raw']for r in rows}),unique_urls=len({r['url']for r in rows}),sample_rows=len(sample),
        sample_http=dict(Counter(r['http_status']for r in sample)),stats=dict(stats),age_cutoff=None,current_only=False,
        pdf_bodies_downloaded=0,scope='All entries reached from the official public manual catalog, including hidden old-model lists; not proof of every historical product',completed_at=now())
    (RAW/f'{key}_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');run(sys.argv[1])

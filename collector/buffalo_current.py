"""Initial BUFFALO batch: default public Wi-Fi router/repeater/adapter lists.

Use product_search and productDetail/manual as called by buffalo.js. Public
manual records only; do not call private-IP authorization or membership APIs.
"""
import json
import random
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup
from collector.common import RAW,LOGS,load_jsonl,now,write_rows,write_jsonl,check_urls
from collector.polite import PoliteClient

SITE='https://www.buffalo.jp'
SLUGS=('ap','extender','client')
MAX_MODELS=250

def run():
    c=PoliteClient(LOGS/'buffalo_current_requests.log',timeout=20,session_per_thread=True)
    catalogs=[];models={};incomplete=[]
    for slug in SLUGS:
        page=SITE+'/product/child_category/'+slug+'.html';r=c.get(page);r.raise_for_status()
        s=BeautifulSoup(r.content,'lxml');tag=s.select_one('.include-small-category-id')
        if tag is None:raise ValueError('Expected public category query not found')
        query=tag.get_text(strip=True);api=SITE+'/api/v1/product_search?'+query
        a=c.get(api);a.raise_for_status();data=a.json()
        entries=[]
        for item in data.get('items',[]):
            f=item['fields'];model=f.get('prm_product_mode_no')or f.get('sap_product_mode_no')or item['id']
            rec={'item_code':item['id'],'model_raw':model,'category':slug,'product_url':urljoin(SITE,f.get('filepath','')),
                 'product_name':f.get('prm_product_name',''),'source_url':page,'api_url':api}
            models[item['id']]=rec;entries.append(rec)
        catalogs.append({'url':api,'source_page':page,'totalHits':data.get('totalHits'),'items':entries,'fetched_at':now()})
        if int(data.get('totalHits',len(entries)))!=len(entries):incomplete.append(slug)
    if not models or len(models)>MAX_MODELS:raise ValueError('Category scope outside predeclared bounds')
    write_jsonl(RAW/'buffalo_current_catalog.jsonl',catalogs)
    path=RAW/'buffalo_current_pages.jsonl';pages={p['item_code']:p for p in load_jsonl(path)if p.get('status')==200}
    todo=[m for code,m in models.items()if code not in pages]
    print(json.dumps({'models':len(models),'remaining':len(todo),'categories_with_more_items':incomplete}),flush=True)
    def one(m):
        try:
            a=c.get(SITE+'/api/v1/productDetail/manual',params={'item_code':m['item_code']})
            data=a.json()if a.status_code==200 else{}
            return dict(m,status=a.status_code,result_code=data.get('result_code'),documents=data.get('result_list',[]),fetched_at=now())
        except Exception as e:return dict(m,status=type(e).__name__,documents=[],error=str(e))
    with path.open('a',encoding='utf-8')as out,ThreadPoolExecutor(max_workers=4)as pool:
        for i,p in enumerate(pool.map(one,todo),1):
            out.write(json.dumps(p,ensure_ascii=False)+'\n');out.flush();pages[p['item_code']]=p
            if i%20==0:print(json.dumps({'fetched':i,'remaining':len(todo)-i}),flush=True)
    rows,evidence,gaps,references=[],[],[],[];private=0
    for code,m in models.items():
        p=pages.get(code,{})
        public=[]
        for d in p.get('documents',[]):
            if d.get('private_group'):private+=1;continue
            if d.get('downloadUrl'):public.append(d)
        if not public:gaps.append(dict(m,status=p.get('status'),reason='no_public_download_url'))
        for d in public:
            u=urljoin(SITE,d['downloadUrl']);host=urlsplit(u).netloc
            if urlsplit(u).path.startswith('/support/faq/'):
                references.append(dict(m,url=u,title=d.get('linkText',''),reason='FAQ_reference_not_a_manual'))
                continue
            if not(host=='www.buffalo.jp'or host=='manual.buffalo.jp'):
                gaps.append(dict(m,reason='external_download_not_collected',document_url=u));continue
            row=dict(maker='バッファロー',domain='通信',product_category=m['category'],model_raw=m['model_raw'],
                model_normalized=unicodedata.normalize('NFKC',m['model_raw']).upper().replace(' ',''),title=d.get('linkText',''),
                url=u,url_type='pdf'if urlsplit(u).path.lower().endswith('.pdf')else'html',source_method='api',first_seen='',
                http_status='',checked_at='',model_unconfirmed='0',discontinued='')
            rows.append(row);evidence.append(dict(row,catalog_api_url=m['api_url'],product_url=m['product_url'],item_code=code,public_group=d.get('private_group','')))
    rows=list({(r['model_raw'],r['url']):r for r in rows}.values())
    sample=random.Random(20261123).sample(rows,min(50,len(rows)))
    statuses=check_urls(c,[r['url']for r in sample],Counter(),workers=2)
    for r in rows:r['http_status'],r['checked_at']=statuses.get(r['url'],('',''))
    write_rows(RAW/'buffalo_current_manuals.csv',rows);write_rows(RAW/'buffalo_current_head_sample.csv',sample)
    write_jsonl(RAW/'buffalo_current_evidence.jsonl',evidence);write_jsonl(RAW/'buffalo_current_gaps.jsonl',gaps)
    write_jsonl(RAW/'buffalo_current_reference_links.jsonl',references)
    summary=dict(scope='default public Wi-Fi router, repeater, adapter representative-model catalogs only',
        models=len(models),rows=len(rows),unique_urls=len({r['url']for r in rows}),gaps=len(gaps),private_records_excluded=private,
        faq_reference_links_excluded=len(references),
        sample_rows=len(sample),sample_http=dict(Counter(r['http_status']for r in sample)),categories_with_more_items=incomplete,
        max_models=MAX_MODELS,completed_at=now())
    (RAW/'buffalo_current_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');run()

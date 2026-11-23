"""First batch from I-O DATA's public support-library update listing.

product.js publishes /lib/script/product.php?code=<library key>. The returned
product.man objects explicitly map the product name to manual URLs. /man/ is
disallowed, but /lib/manual/ is a different, permitted public manual directory.
"""
import json
import random
import re
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup
from collector.common import RAW,LOGS,load_jsonl,now,write_rows,write_jsonl,check_urls
from collector.polite import PoliteClient

SITE='https://www.iodata.jp'
MAX_MODELS=300

def run():
    c=PoliteClient(LOGS/'iodata_requests.log',timeout=20,session_per_thread=True)
    r=c.get(SITE+'/lib/');r.raise_for_status()
    s=BeautifulSoup(r.content,'lxml')
    models={}
    for a in s.select('a[href]'):
        u=urljoin(r.url,a['href']);p=urlsplit(u)
        m=re.fullmatch(r'/lib/product/[^/]+/(\d+)\.htm',p.path)
        if p.netloc=='www.iodata.jp'and m:
            models[m[1]]={'code':m[1],'url':u,'label':a.get_text(' ',strip=True)}
    if not models or len(models)>MAX_MODELS:
        raise ValueError(f'Unexpected library-entry scope: {len(models)}')
    write_jsonl(RAW/'iodata_models.jsonl',models.values())
    path=RAW/'iodata_pages.jsonl'
    pages={p['code']:p for p in load_jsonl(path)if p.get('status')==200}
    todo=[p for p in models.values()if p['code']not in pages]
    print(json.dumps({'library_models':len(models),'remaining':len(todo)}),flush=True)
    def one(m):
        try:
            a=c.get(SITE+'/lib/script/product.php',params={'code':m['code']})
            return {'code':m['code'],'source_model':m,'status':a.status_code,'api_url':a.url,'data':a.json()if a.status_code==200 else {},'fetched_at':now()}
        except Exception as e:return {'code':m['code'],'source_model':m,'status':type(e).__name__,'error':str(e)}
    with path.open('a',encoding='utf-8')as out,ThreadPoolExecutor(max_workers=3)as pool:
        for i,p in enumerate(pool.map(one,todo),1):
            out.write(json.dumps(p,ensure_ascii=False)+'\n');out.flush();pages[p['code']]=p
            if i%20==0:print(json.dumps({'fetched':i,'remaining':len(todo)-i}),flush=True)
    rows,evidence,gaps=[],[],[]
    for code in models:
        p=pages.get(code,{})
        product=p.get('data',{}).get('product',{})
        name=product.get('name','')
        docs=[{'url':urljoin(SITE,d['File_Name']),'title':d.get('Title','')}for d in product.get('man',[])if d.get('File_Name')]
        for a in BeautifulSoup(product.get('manual',''),'lxml').select('a[href]'):
            docs.append({'url':urljoin(SITE,a['href']),'title':a.get_text(' ',strip=True)})
        if not name or not docs:
            gaps.append({'code':code,'name':name,'status':p.get('status'),'reason':'product_name_or_manual_missing'});continue
        for d in docs:
            host=urlsplit(d['url']).netloc
            if host!='www.iodata.jp'and not host.endswith('.iodata.jp'):
                gaps.append({'code':code,'name':name,'reason':'external_link_not_collected','document':d});continue
            row=dict(maker='アイ・オー・データ',domain='通信',product_category=product.get('spec',''),
                model_raw=name,model_normalized=unicodedata.normalize('NFKC',name).upper().replace(' ',''),
                title=d['title'],url=d['url'],url_type='pdf'if urlsplit(d['url']).path.lower().endswith('.pdf')else'html',
                source_method='api',first_seen='',http_status='',checked_at='',model_unconfirmed='0',discontinued='')
            rows.append(row);evidence.append(dict(row,library_url=models[code]['url'],api_url=p.get('api_url')))
    rows=list({(x['model_raw'],x['url']):x for x in rows}.values())
    sample=random.Random(20261123).sample(rows,min(50,len(rows)))
    stats=Counter();statuses=check_urls(c,[r['url']for r in sample],stats,workers=2)
    for row in rows:row['http_status'],row['checked_at']=statuses.get(row['url'],('',''))
    write_rows(RAW/'iodata_manuals.csv',sorted(rows,key=lambda r:(r['model_raw'],r['url'])))
    write_rows(RAW/'iodata_head_sample.csv',sample)
    write_jsonl(RAW/'iodata_evidence.jsonl',evidence);write_jsonl(RAW/'iodata_gaps.jsonl',gaps)
    summary=dict(scope='public /lib/ update-listing batch only, not entire product catalog',source_url=SITE+'/lib/',
        library_entries=len(models),models=len({r['model_raw']for r in rows}),rows=len(rows),unique_urls=len({r['url']for r in rows}),
        gaps=len(gaps),sample_rows=len(sample),sample_http=dict(Counter(r['http_status']for r in sample)),
        max_models=MAX_MODELS,completed_at=now(),**stats)
    (RAW/'iodata_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');run()

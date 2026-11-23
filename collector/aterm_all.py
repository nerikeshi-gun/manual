"""Current and support-ended Aterm manual catalogs, including shared ISDN pages.

manual2/support/manual is an errata index, not the old-product manual catalog.
The actual support-ended entry point is support/manual/index2.html.
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
from collector.common import RAW,LOGS,now,load_jsonl,write_jsonl,write_rows,check_urls,decode
from collector.polite import PoliteClient

SITE='https://www.aterm.jp'
ROOTS=[SITE+'/support/manual/',SITE+'/support/manual/index2.html']
def norm_url(source,href):
    u=urljoin(source,href).split('#')[0]
    if u.startswith('http://www.aterm.jp/'):u='https://'+u[7:]
    return u

def run():
    c=PoliteClient(LOGS/'aterm_all_requests.log',timeout=20,session_per_thread=True)
    path=RAW/'aterm_all_pages.jsonl';cache={p['url']:p for p in load_jsonl(path)if p.get('status')==200}
    queue={u:dict(url=u,kind='catalog',source_url='')for u in ROOTS};seen=set();pages={}
    def one(seed):
        if seed['url']in cache:return cache[seed['url']]
        try:
            r=c.get(seed['url'],stream=True);r.raise_for_status()
            if 'html'not in r.headers.get('content-type',''):r.close();raise ValueError('Expected HTML')
            s=BeautifulSoup(decode(r),'lxml');r.close();content=s.select_one('#mainContents')or s
            heading=s.title.get_text(' ',strip=True)if s.title else''
            links=[];documents=[]
            for a in content.select('a[href]'):
                u=norm_url(r.url,a['href']);p=urlsplit(u)
                if p.netloc!='www.aterm.jp':continue
                label=a.get_text(' ',strip=True)
                if re.fullmatch(r'/support/manual/[a-z0-9_-]+/index\.html',p.path):
                    links.append(dict(url=u,kind='model',model_hint=label,source_url=r.url))
                elif re.fullmatch(r'/support/manual2/manual/download_[a-z0-9_]+\.html',p.path):
                    links.append(dict(url=u,kind='shared_legacy',source_url=r.url))
            def docs(box,model,section):
                for a in box.select('a[href]'):
                    u=norm_url(r.url,a['href']);p=urlsplit(u);title=a.get_text(' ',strip=True)
                    if p.netloc!='www.aterm.jp'or not title:continue
                    pdf=p.path.lower().endswith('.pdf')
                    manual_html=('/guide/'in p.path or '/function/'in p.path)and p.path.lower().endswith(('.html','.htm','/'))
                    if pdf or manual_html:documents.append(dict(model_raw=model,title=title,url=u,url_type='pdf'if pdf else'html',section=section))
            if seed['kind']=='model':
                # The first h1 is a site-wide support slogan on newer pages.
                # The document title starts with the explicit product name.
                title=heading.split('｜')[0].strip()
                model=re.sub(r'^Aterm\s*','',title).strip()
                model=re.split(r'\s*(?:マニュアル|取扱説明書|｜)',model,maxsplit=1)[0].strip(' ：:')
                if not re.search(r'[A-Za-z].*\d|\d.*[A-Za-z]',model):model=''
                docs(content,model,title)
            elif seed['kind']=='shared_legacy':
                for h in content.select('h3[id]'):
                    label=h.get_text(' ',strip=True);model=re.sub(r'^Aterm\s*','',label).strip()
                    for sibling in h.next_siblings:
                        if getattr(sibling,'name',None)in ('h2','h3'):break
                        if hasattr(sibling,'select'):docs(sibling,model,label)
            return dict(seed,status=r.status_code,title=heading,links=links,documents=documents,fetched_at=now())
        except Exception as e:return dict(seed,status=type(e).__name__,links=[],documents=[],error=str(e),fetched_at=now())
    while queue:
        batch=[x for u,x in queue.items()if u not in seen];queue={}
        if not batch:break
        with ThreadPoolExecutor(max_workers=6)as pool,path.open('a',encoding='utf-8')as out:
            for p in pool.map(one,batch):
                pages[p['url']]=p;seen.add(p['url']);out.write(json.dumps(p,ensure_ascii=False)+'\n');out.flush()
                for x in p['links']:
                    if x['url']not in seen:queue.setdefault(x['url'],x)
        print(json.dumps(dict(pages=len(seen),pending=len(queue))),flush=True)
    rows=[];evidence=[];gaps=[]
    for p in pages.values():
        if p['kind']!='catalog'and not p.get('documents'):gaps.append(p)
        for d in p.get('documents',[]):
            m=d['model_raw']
            if p['kind']=='model':
                m=re.sub(r'^Aterm\s*','',p['title'].split('｜')[0]).strip()
                if not re.search(r'[A-Za-z].*\d|\d.*[A-Za-z]',m):m=''
            row=dict(maker='NEC（Aterm）',domain='通信',product_category='ルーター・ISDN機器',model_raw=m,
                model_normalized=unicodedata.normalize('NFKC',m).upper(),title=d['title'],url=d['url'],url_type=d['url_type'],source_method='crawl',first_seen='',
                http_status='',checked_at='',model_unconfirmed='0'if m else'1',discontinued='')
            rows.append(row);evidence.append(dict(row,source_url=p['url'],source_kind=p['kind'],section=d['section'],fetched_at=p['fetched_at']))
    rows=list({(r['model_raw'],r['url']):r for r in rows}.values())
    sample=random.Random(20261123).sample(rows,min(50,len(rows)));stats=Counter();statuses=check_urls(c,[r['url']for r in sample],stats,workers=3)
    for r in rows:
        if r['url']in statuses:r['http_status'],r['checked_at']=statuses[r['url']]
    write_rows(RAW/'aterm_all_manuals.csv',rows);write_rows(RAW/'aterm_all_head_sample.csv',sample)
    write_jsonl(RAW/'aterm_all_evidence.jsonl',evidence);write_jsonl(RAW/'aterm_all_gaps.jsonl',gaps)
    summary=dict(source_pages=len(seen),source_kinds=dict(Counter(p['kind']for p in pages.values())),failed_pages=sum(p['status']!=200 for p in pages.values()),
        pages_without_documents=len(gaps),rows=len(rows),models=len({r['model_raw']for r in rows}),unique_urls=len({r['url']for r in rows}),
        sample_rows=len(sample),sample_http=dict(Counter(r['http_status']for r in sample)),stats=dict(stats),age_cutoff=None,pdf_bodies_downloaded=0,completed_at=now())
    (RAW/'aterm_all_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');run()

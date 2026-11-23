"""Collect explicitly linked manual PDFs from Paloma's public update archive.

The blocked Salesforce search service is not visited. This is an archive batch,
not a claim that all Paloma product manuals have been collected.
"""
import json
import random
import re
import sys
import unicodedata
from collections import Counter,deque
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup
from collector.common import RAW,LOGS,now,write_rows,write_jsonl,check_urls
from collector.polite import PoliteClient

ROOT='https://www.paloma.co.jp/support/info/index.html'
MAX_PAGES=80

def run():
    c=PoliteClient(LOGS/'paloma_requests.log',timeout=20)
    queue=deque([ROOT]);seen=set();pages=[];docs=[]
    while queue and len(seen)<MAX_PAGES:
        u=queue.popleft()
        if u in seen:continue
        seen.add(u)
        try:
            r=c.get(u);s=BeautifulSoup(r.content,'lxml');links=[]
            if r.status_code==200:
                for a in s.select('a[href]'):
                    target=urljoin(r.url,a['href']).split('#')[0];p=urlsplit(target);label=a.get_text(' ',strip=True)
                    if p.netloc!='www.paloma.co.jp':continue
                    if p.path.startswith('/support/info/')and p.path.endswith(('.html','.htm')):
                        if target not in seen:queue.append(target)
                    if p.path.lower().endswith('.pdf')and re.search(r'取扱説明書|工事説明書|施工説明書|設置説明書',label):
                        d={'url':target,'label':label,'source_url':u};docs.append(d);links.append(d)
            pages.append({'url':u,'status':r.status_code,'manual_links':links,'fetched_at':now()})
        except Exception as e:pages.append({'url':u,'status':type(e).__name__,'error':str(e)})
    rows,evidence=[],[]
    for d in docs:
        names=list(dict.fromkeys(re.findall(r'(?<![A-Z0-9])[A-Z][A-Z0-9]*(?:-[A-Z0-9()]+)+(?![A-Z0-9])',unicodedata.normalize('NFKC',d['label']))))or['']
        for model in names:
            row=dict(maker='パロマ',domain='住設',product_category='ガス機器・関連部材',model_raw=model,model_normalized=model.upper(),
                title=d['label'],url=d['url'],url_type='pdf',source_method='crawl',first_seen='',http_status='',checked_at='',
                model_unconfirmed='0'if model else'1',discontinued='')
            rows.append(row);evidence.append(dict(row,source_url=d['source_url'],source_label=d['label']))
    rows=list({(r['model_raw'],r['url']):r for r in rows}.values())
    sample=random.Random(20261123).sample(rows,min(50,len(rows)))
    statuses=check_urls(c,[r['url']for r in sample],Counter(),workers=1)
    for r in rows:r['http_status'],r['checked_at']=statuses.get(r['url'],('',''))
    write_rows(RAW/'paloma_manuals.csv',rows);write_rows(RAW/'paloma_head_sample.csv',sample)
    write_jsonl(RAW/'paloma_pages.jsonl',pages);write_jsonl(RAW/'paloma_evidence.jsonl',evidence)
    summary=dict(scope='public support update-archive manual links only; not full product catalog',pages=len(pages),
        pages_failed=sum(p['status']!=200 for p in pages),remaining_pages=len(set(queue)-seen),rows=len(rows),
        models=len({r['model_raw']for r in rows if r['model_raw']}),unique_urls=len({r['url']for r in rows}),
        sample_rows=len(sample),sample_http=dict(Counter(r['http_status']for r in sample)),max_pages=MAX_PAGES,completed_at=now())
    (RAW/'paloma_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');run()

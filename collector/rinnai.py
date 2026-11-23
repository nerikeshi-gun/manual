"""Rinnai public anonymous manual search, seeded by explicit catalog models."""
import json
import re
from collections import Counter
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from collector.common import RAW, LOGS, now, write_rows, write_jsonl
from collector.polite import PoliteClient

CATALOG='https://rinnai.jp/products/kitchen/gas_table/gt_metal/gt_metal_lineup'
BASE='https://rkids.rinnai.jp/rin/cgi-bin/'

def soup(r):
    r.raise_for_status()
    if 'html' not in r.headers.get('content-type','').lower():
        raise ValueError('Expected HTML, will not read download body')
    return BeautifulSoup(r.content,'lxml')

def run():
    c=PoliteClient(LOGS/'rinnai_requests.log',timeout=25)
    r=c.get(CATALOG);s=soup(r)
    models=list(dict.fromkeys(re.findall(r'\bRT64(?:MH7R2-C[LR]|JH7S2-C[LR]|JH6S2-G[LR]|-2H6S-[LR])\b',str(s))))
    if len(models)!=8:raise ValueError('Expected eight explicitly published catalog models')
    evidence=[dict(source_url=CATALOG,models=models,fetched_at=now())]
    soup(c.get(BASE+'xauth.cgi?str1=manual'))
    rows=[];gaps=[]
    for model in models:
        r=c.post(BASE+'itemSearch.cgi',data=dict(item_search_type=model,page='1',search_mode='type',header_type='manual'),allow_redirects=False,stream=True)
        if r.is_redirect:
            u=urljoin(r.url,r.headers['location']);r.close();r=c.get(u)
        s=soup(r);details=[]
        for tr in s.select('tr'):
            if model not in tr.get_text(' ',strip=True):continue
            for a in tr.select('a[href]'):
                if 'itemDetail.cgi?' in a['href']:
                    details.append(urljoin(r.url,a['href']))
        links=[]
        for u in dict.fromkeys(details):
            dr=c.get(u);ds=soup(dr)
            # Require an exact model field on the official detail page.
            cells=[x.get_text(' ',strip=True) for x in ds.select('td')]
            if model not in cells:raise ValueError('Detail model did not match '+model)
            for tr in ds.select('tr'):
                for a in tr.select('a[href]'):
                    if 'imageDownload.cgi?' not in a['href']:continue
                    label=tr.get_text(' ',strip=True)
                    if '取扱説明書' not in label:continue
                    du=urljoin(dr.url,a['href']);hr=c.head_or_range(du)
                    ct=hr.headers.get('content-type','');hr.close()
                    # Authentication-error HTML must not be reported as a live PDF.
                    ok=hr.status_code==200 and any(t in ct.lower() for t in ('pdf','octet-stream','force-download'))
                    links.append(dict(url=du,label=label,source_url=dr.url,http_status=hr.status_code,content_type=ct,download_header_verified=ok))
                    rows.append(dict(maker='リンナイ',domain='住設',product_category='ガステーブル',model_raw=model,model_normalized=model,
                        title=label,url=du,url_type='pdf',source_method='crawl',first_seen='',http_status=str(hr.status_code) if ok else '',
                        checked_at=now() if ok else '',model_unconfirmed='0',discontinued=''))
        evidence.append(dict(model=model,search_url=BASE+'itemSearch.cgi',detail_urls=list(dict.fromkeys(details)),links=links,fetched_at=now()))
        if not links:gaps.append(model)
        print(model,len(links),flush=True)
    rows=list({(r['model_raw'],r['url']):r for r in rows}.values())
    write_rows(RAW/'rinnai_manuals.csv',rows);write_jsonl(RAW/'rinnai_evidence.jsonl',evidence)
    summary=dict(catalog_models=len(models),models_with_manuals=len({r['model_raw']for r in rows}),rows=len(rows),unique_urls=len({r['url']for r in rows}),
        http=dict(Counter(r['http_status']for r in rows)),gaps=gaps,anonymous_public_session=True,pdf_bodies_downloaded=0,completed_at=now())
    (RAW/'rinnai_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':run()

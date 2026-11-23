"""Daikin's publicly linked remote-controller and DK-CONNECT manuals."""
import json
import re
from collections import Counter
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from collector.common import RAW,LOGS,now,write_rows,write_jsonl,check_urls
from collector.polite import PoliteClient

SEEDS=['https://www.ac.daikin.co.jp/remocon_pa/manual','https://www.ac.daikin.co.jp/solution/dkconnect/document']

def run():
    c=PoliteClient(LOGS/'daikin_public_requests.log',timeout=25)
    rows=[];evidence=[]
    def add(models,label,a,source,context,category):
        u=urljoin(source,a['href'])
        evidence.append(dict(models=models,title=label,url=u,source_url=source,context=context,fetched_at=now()))
        for m in models or ['']:
            rows.append(dict(maker='ダイキン',domain='家電',product_category=category,model_raw=m,model_normalized=m,
                title=label,url=u,url_type='pdf',source_method='crawl',first_seen='',http_status='',checked_at='',model_unconfirmed='0' if m else '1',discontinued=''))
    for seed in SEEDS:
        r=c.get(seed);r.raise_for_status();s=BeautifulSoup(r.content,'lxml')
        if 'remocon_pa' in seed:
            for h in s.find_all('h4'):
                model=h.get_text(' ',strip=True)
                if not re.fullmatch(r'BRC1G\d(?:\(K\))?',model):continue
                table=h.find_next('table');a=table.select_one('a.g-pdf[href]')
                if not a:raise ValueError('Missing controller manual')
                add([model],'取扱説明書',a,r.url,model+' '+table.get_text(' ',strip=True),'業務用エアコンリモコン')
            for table in s.find_all('table'):
                if 'BYCP160EEGF' not in table.get_text():continue
                carried=[]
                for tr in table.select('tr'):
                    text=tr.get_text(' ',strip=True)
                    models=re.findall(r'\b(?:BYCP|BDSP)[A-Z0-9]+\b',text)
                    if models:carried=models
                    for a in tr.select('a.g-pdf[href]'):
                        title='取付説明書' if '取付説明書' in text else '取扱説明書'
                        add(carried,title,a,r.url,text,'業務用エアコンパネル・キット')
            for a in s.select('a.g-pdf[href]'):
                if 'M17A034' in a['href']:
                    add([],'スゴ暖ZEAS向け 別冊 高暖房モード操作説明書',a,r.url,'スゴ暖ZEAS向け。対応する型式番号は一覧に明記なし','業務用エアコン')
        else:
            for a in s.select('a[href]'):
                if '/solution/dkconnect/document/data/' not in a['href'] or '.pdf' not in a['href']:continue
                label=a.get_text(' ',strip=True)
                add(['DK-CONNECT'],'取扱説明書 '+label,a,r.url,label,'空調集中管理システム')
    rows=list({(r['model_raw'],r['url']):r for r in rows}.values())
    stats=Counter();statuses=check_urls(c,[r['url']for r in rows],stats,workers=3)
    for r in rows:r['http_status'],r['checked_at']=statuses[r['url']]
    write_rows(RAW/'daikin_public_manuals.csv',rows);write_jsonl(RAW/'daikin_public_evidence.jsonl',evidence)
    summary=dict(rows=len(rows),models=len({r['model_raw']for r in rows if r['model_raw']}),unique_urls=len(statuses),http=dict(Counter(r['http_status']for r in rows)),
        stats=dict(stats),model_unconfirmed=sum(r['model_unconfirmed']=='1'for r in rows),pdf_bodies_downloaded=0,completed_at=now())
    (RAW/'daikin_public_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':run()

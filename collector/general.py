"""Initial GENERAL room-airconditioner batch from public HTML manual covers.

No model-search API, embedded API key or browser interaction is used.
Seeds were discovered as official HTML manual URLs in public web search.
"""
import json
import re
from collections import Counter
from bs4 import BeautifulSoup
from collector.common import RAW,LOGS,now,write_jsonl,write_rows,check_urls
from collector.polite import PoliteClient

SEEDS=[
 'https://www.generalww.com/data/html-manual/jp-airconditioner/ja/2025/lineup/nocria-ch/index.html',
 'https://www.generalww.com/data/html-manual/jp-airconditioner/ja/2025/lineup/nocria-ee/index.html',
]

def run():
    c=PoliteClient(LOGS/'general_requests.log',timeout=20)
    rows,evidence=[],[]
    for u in SEEDS:
        r=c.get(u);r.raise_for_status();s=BeautifulSoup(r.content,'lxml')
        box=s.select_one('#cover-type');title=s.title.get_text(' ',strip=True)if s.title else ''
        if not box or '取扱説明書'not in title:
            raise ValueError('Manual cover did not match expected public layout')
        cover=box.get_text(' ',strip=True)
        models=list(dict.fromkeys(re.findall(r'(?<![A-Z0-9])(?:AS|AO)-[A-Z0-9-]+',cover)))
        if not models:raise ValueError('No explicit model names on manual cover')
        evidence.append({'url':r.url,'title':title,'model_cover':cover,'models':models,'status':r.status_code,'fetched_at':now()})
        for model in models:
            rows.append(dict(maker='ゼネラル',domain='家電',product_category='ルームエアコン',model_raw=model,
                model_normalized=model,title=title,url=r.url,url_type='html',source_method='crawl',first_seen='',
                http_status='',checked_at='',model_unconfirmed='0',discontinued=''))
    statuses=check_urls(c,[r['url']for r in rows],Counter(),workers=1)
    for r in rows:r['http_status'],r['checked_at']=statuses[r['url']]
    write_rows(RAW/'general_manuals.csv',rows);write_jsonl(RAW/'general_evidence.jsonl',evidence)
    summary=dict(scope='2025 CH/EE series public HTML manuals only; other years and series remain',
        rows=len(rows),models=len({r['model_raw']for r in rows}),unique_urls=len(statuses),
        http=dict(Counter(r['http_status']for r in rows)),source_models='explicit cover-type list, indoor and outdoor units',
        completed_at=now(),search_api_used=False,pdf_bodies_downloaded=0)
    (RAW/'general_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':run()

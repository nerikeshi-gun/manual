"""Official FAQ-linked care manual plus explicitly indexed product manuals."""
import csv
import json
from collections import Counter
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from collector.index_manuals import run as indexed
from collector.common import RAW,LOGS,now,load_jsonl,write_rows,write_jsonl
from collector.polite import PoliteClient

def run():
    key='takara_standard';indexed(key)
    rows=list(csv.DictReader((RAW/f'{key}_manuals.csv').open(encoding='utf-8',newline='')))
    evidence=load_jsonl(RAW/f'{key}_evidence.jsonl')
    c=PoliteClient(LOGS/'takara_public_requests.log',timeout=20)
    source='https://qa.takara-standard.co.jp/fa/pblc/web/knowledge1708.html'
    r=c.get(source);r.raise_for_status();s=BeautifulSoup(r.content,'lxml')
    a=next(a for a in s.select('a[href]')if a.get_text(' ',strip=True)=='お手入れマニュアル')
    u=urljoin(r.url,a['href']);r=c.get(u,stream=True);r.raise_for_status()
    if 'html'not in r.headers.get('content-type',''):r.close();raise ValueError('Expected public HTML manual viewer')
    s=BeautifulSoup(r.content,'lxml');title=s.title.get_text(' ',strip=True)
    if 'タカラスタンダード株式会社'not in title or '水まわりお手入れマニュアル'not in title:raise ValueError('Manual publisher/title mismatch')
    rows.append(dict(maker='タカラスタンダード',domain='住設',product_category='水まわりお手入れ',model_raw='',model_normalized='',title='水まわりお手入れマニュアル',
        url=u,url_type='html',source_method='crawl',first_seen='',http_status=str(r.status_code),checked_at=now(),model_unconfirmed='1',discontinued=''))
    evidence.append(dict(source_url=source,url=u,resolved_url=r.url,title=title,model_raw='',model_unconfirmed=True,http_status=r.status_code,checked_at=now(),
        discovery_method='live_official_faq_link',verification_method='HTML viewer publisher and title only; pages/model coverage not inspected'))
    r.close();write_rows(RAW/f'{key}_manuals.csv',rows);write_jsonl(RAW/f'{key}_evidence.jsonl',evidence)
    summary=dict(rows=len(rows),models=len({r['model_raw']for r in rows if r['model_raw']}),unique_urls=len({r['url']for r in rows}),
        model_unconfirmed=sum(r['model_unconfirmed']=='1'for r in rows),http=dict(Counter(r['http_status']for r in rows)),
        indexed_metadata_rows=len(rows)-1,live_html_manuals=1,pdf_bodies_downloaded=0,pdf_model_match_rate=None,completed_at=now())
    (RAW/f'{key}_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':run()

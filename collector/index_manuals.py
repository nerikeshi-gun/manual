"""Build explicitly sourced official-index supplements without fetching PDF bodies.

The seed JSON records are factual URL/model metadata discovered in public search
results for official pages. Robots restrictions are never bypassed. These are
not live-crawled catalogs and must be documented as partial index supplements.
"""
import json
import sys
from collections import Counter
from collector.common import RAW,LOGS,now,write_rows,write_jsonl,check_urls
from collector.polite import PoliteClient

def run(key):
    seeds=json.loads((RAW/f'{key}_index_seeds.json').read_text(encoding='utf-8'))
    c=PoliteClient(LOGS/f'{key}_index_requests.log',timeout=20)
    stats=Counter();statuses=check_urls(c,[x['url']for x in seeds],stats,workers=1)
    rows=[];evidence=[]
    for x in seeds:
        status,date=statuses[x['url']]
        row={k:x[k]for k in ['maker','domain','product_category','model_raw','title','url']}
        row.update(model_normalized=x['model_raw'],url_type='pdf',source_method='crawl',first_seen='',http_status=status,checked_at=date,
            model_unconfirmed='0'if x['model_raw']else'1',discontinued='')
        rows.append(row)
        evidence.append(dict(x,discovery_method='official_public_search_index',direct_source_page_crawled=False,
            verification_method='official_index_metadata_only',http_status=status,checked_at=date,robots_allowed=c.can_fetch(x['url']),recorded_at=now()))
    write_rows(RAW/f'{key}_manuals.csv',rows);write_jsonl(RAW/f'{key}_evidence.jsonl',evidence)
    summary=dict(rows=len(rows),models=len({r['model_raw']for r in rows if r['model_raw']}),unique_urls=len(statuses),
        http=dict(Counter(r['http_status']for r in rows)),stats=dict(stats),scope='Explicit official public search-index metadata only; not a catalog crawl',
        source_method_note='crawl is the existing CSV enum for page-derived metadata; actual discovery and absence of live source fetch are recorded in evidence',
        pdf_bodies_downloaded=0,pdf_model_match_rate=None,completed_at=now())
    (RAW/f'{key}_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':run(sys.argv[1])

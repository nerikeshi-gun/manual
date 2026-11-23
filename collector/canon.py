"""Canon Japanese manual sitemap plus the Japan-region IJ manual selector.

No age cut-off or current-product filter. All discovered source pages are
checkpointed, including failures and pages without supported document links.
"""
import json
import random
import re
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin,urlsplit,quote
from bs4 import BeautifulSoup
from collector.common import RAW,LOGS,now,load_jsonl,write_jsonl,write_rows,check_urls
from collector.polite import PoliteClient

SITEMAP='https://canon.jp/sitemap.xml'
PORTAL='https://ij.manual.canon/ij/webmanual/WebPortal/PTL/ptl-select.html?lng=jp&type=manual&area=jp'
DOC_HOSTS={'canon.jp','ij.manual.canon','cam.start.canon','oip.manual.canon','gdlp01.c-wss.com','gdlp02.c-wss.com','pdisp01.c-wss.com'}
CAMERA_GROUPS={'eosd','digitalcamera','ef','webview','binoculars','dvcamera','prodv','cinema-eos','remotecam','robocame'}
CATEGORY={'albos':'ライト・スピーカー','binoculars':'双眼鏡','digitalcamera':'デジタルカメラ','eosd':'カメラ・カメラ周辺機器','filmcamera':'フィルムカメラ',
 'ef':'レンズ','ef-cinemalens':'シネマレンズ','bctv':'放送用レンズ','dictionary':'電子辞書','calculators':'電卓','canoscan':'スキャナー','dr':'ドキュメントスキャナー',
 'scanfront':'ネットワークスキャナー','dvcamera':'ビデオカメラ','prodv':'業務用ビデオカメラ','cinema-eos':'映像機器','projector':'プロジェクター',
 'webview':'ネットワークカメラ','remotecam':'リモートカメラ','robocame':'ロボットカメラ','edge':'ネットワークカメラ','ht':'ハンディターミナル',
 'software':'ソフトウェア','apps':'ソフトウェア','imageprograf':'大判プリンター','imagepress':'業務用複合機'}

def source_category(p):
    parts=urlsplit(p['url']).path.removeprefix('/support/manual/').split('/')
    group=parts[1]if parts[0]=='guide'and len(parts)>1 else parts[0]
    return CATEGORY.get(group,p.get('category')or'電子機器')

def software_source(u):
    tail=urlsplit(u).path.removeprefix('/support/manual/')
    return bool(re.match(r'(?:software|apps)(?:/|$)|eosd/soft(?:-old)?$|bj/mct(?:mac|win)$|mp/(?:epd|mig|qm|pa)$',tail))

def heading_model(h,u):
    leaf=len(urlsplit(u).path.removeprefix('/support/manual/').strip('/').split('/'))>1
    prefix=re.split(r'商品マニュアル|製品マニュアル|マニュアルダウンロード',h,maxsplit=1)[0].strip(' \u3000：:')
    # Some product pages end in 商品マニュアル一覧. The suffix 一覧 alone
    # does not make the explicit product prefix a category. Reject a bare
    # 旧 prefix from 旧商品マニュアル and generic category headings instead.
    explicit_single=leaf or bool(re.search(r'\b[A-Z]+[A-Z0-9]*-[A-Z0-9]+',prefix))
    if explicit_single and prefix and prefix!=h and prefix not in ('旧','旧商品','商品') and not any(t in prefix for t in ('一覧','電子マニュアル')):
        return prefix
    return ''

def section_model(title,section):
    prefix=re.split(r'使用説明書|取扱説明書|ユーザーズガイド|ユーザーガイド|スタートガイド|詳細ガイド',title,maxsplit=1)[0].strip(' \u3000：:')
    candidates=[(prefix,'document_title_prefix')]if prefix!=title else[]
    candidates.append((section,'section_heading'))
    for value,method in candidates:
        if not value or len(value)>160 or any(t in value for t in ('注意','場合','方法','Windows','Macintosh','アップデート','バージョン','Version')):continue
        if re.search(r'[A-Za-z][A-Za-z0-9 -]*\d|\d[A-Za-z]',value):return value,method
    return '', 'unconfirmed'

def html(c,u):
    r=c.get(u,stream=True)
    r.raise_for_status()
    if 'html' not in r.headers.get('content-type','').lower():
        r.close();raise ValueError('Refusing non-HTML document body')
    s=BeautifulSoup(r.content,'lxml');r.close();return r,s

def run():
    c=PoliteClient(LOGS/'canon_requests.log',timeout=25,session_per_thread=True)
    if '--resume-inventory' in sys.argv:
        sources=load_jsonl(RAW/'canon_sources.jsonl')
        source_urls=[x['url']for x in sources if x['kind']=='jp_sitemap']
        models=[x['model']for x in sources if x['kind']=='ij_japan_selector']
    else:
        r=c.get(SITEMAP);r.raise_for_status();s=BeautifulSoup(r.content,'xml')
        source_urls=sorted({x.get_text(strip=True)for x in s.find_all('loc')if x.get_text(strip=True).startswith('https://canon.jp/support/manual/')})
        r,s=html(c,PORTAL)
        models=list(dict.fromkeys(a['value']for a in s.select('a.model_link[value]')if a['value']))
        sources=[dict(url=u,kind='jp_sitemap',discovery_url=SITEMAP)for u in source_urls]
        sources += [dict(url=PORTAL+'&mdl='+quote(m,safe='')+'&nid=',kind='ij_japan_selector',model=m,discovery_url=PORTAL)for m in models]
    write_jsonl(RAW/'canon_sources.jsonl',sources)
    path=RAW/'canon_pages.jsonl'
    def current(p):
        group=urlsplit(p['url']).path.removeprefix('/support/manual/').split('/')[0]
        # Earlier checkpoints did not recognize the official camera download
        # redirect service. Revisit the affected manual families, preserving
        # successful unrelated work and non-download Wi-Fi tutorial pages.
        upgrade=(group in CAMERA_GROUPS and '/wi-fi/'not in p['url'] and not p['url'].endswith('/wi-fi'))
        needs_sections=p['kind']=='jp_sitemap' and p.get('documents') and not heading_model(p['heading'],p['url'])
        return p.get('status')==200 and (not upgrade or p.get('parser_version',0)>=2) and (not needs_sections or p.get('parser_version',0)>=3)
    pages={p['url']:p for p in load_jsonl(path)if current(p)}
    todo=[x for x in sources if x['url']not in pages]
    print(json.dumps(dict(sitemap_pages=len(source_urls),ij_japan_models=len(models),remaining=len(todo))),flush=True)
    def one(seed):
        try:
            r,s=html(c,seed['url']);content=s.select_one('#content')or s
            heading=content.select_one('h1.hdg .main')or content.select_one('h1.hdg')or content.select_one('h1')
            h=heading.get_text(' ',strip=True)if heading else ''
            category=content.select_one('h1.hdg .sub');category=category.get_text(' ',strip=True)if category else 'プリンター・スキャナー'
            model=seed.get('model','')
            if seed['kind']=='jp_sitemap':
                # Product-specific headings are authoritative; never infer a
                # model from a URL slug or PDF filename.
                model=heading_model(h,seed['url'])
            docs=[]
            if seed['kind']=='ij_japan_selector':
                p=urlsplit(r.url)
                if p.netloc=='ij.manual.canon' and '/ij/webmanual/Manual/'in p.path and '/JP/'in p.path:
                    docs.append(dict(url=r.url,title=s.title.get_text(' ',strip=True)if s.title else 'オンラインマニュアル',url_type='html',model_raw=model,
                        model_mentioned_on_page=model.lower()in s.get_text(' ',strip=True).lower(),http_status='200',checked_at=now()))
            else:
                for a in content.select('a[href]'):
                    u=urljoin(r.url,a['href']);p=urlsplit(u)
                    if p.netloc not in DOC_HOSTS:continue
                    title=a.get_text(' ',strip=True)
                    is_pdf=p.path.lower().endswith('.pdf')or(p.netloc=='pdisp01.c-wss.com'and p.path=='/gdl/WWUFORedirectTarget.do')
                    is_html=(p.netloc in {'ij.manual.canon','cam.start.canon','oip.manual.canon'} and p.path.lower().endswith(('.html','.htm','/')))
                    if not(is_pdf or is_html):continue
                    if not title:continue
                    # Navigation and site-wide assets are not manual records.
                    if any(t in title for t in ('個人情報','カタログ','プライバシー')):continue
                    section=a.find_previous(['h2','h3','h4']);section=section.get_text(' ',strip=True)if section else''
                    doc_model,assignment=(model,'product_heading')if model else section_model(title,section)
                    docs.append(dict(url=u,title=title,url_type='pdf'if is_pdf else'html',model_raw=doc_model,section_heading=section,model_assignment=assignment,http_status='',checked_at=''))
            return dict(seed,status=r.status_code,resolved_url=r.url,heading=h,category=category,documents=docs,parser_version=3,
                discontinued_explicit='生産終了' in h or '販売終了' in h,fetched_at=now())
        except Exception as e:return dict(seed,status=type(e).__name__,documents=[],error=str(e),fetched_at=now())
    with path.open('a',encoding='utf-8')as out,ThreadPoolExecutor(max_workers=8)as pool:
        for i,p in enumerate(pool.map(one,todo),1):
            out.write(json.dumps(p,ensure_ascii=False)+'\n');out.flush();pages[p['url']]=p
            if i%25==0:print(json.dumps(dict(processed=i,total=len(todo),failures=sum(x.get('status')!=200 for x in pages.values()))),flush=True)
    rows=[];evidence=[];gaps=[]
    for seed in sources:
        p=pages.get(seed['url'],{})
        if p.get('status')!=200 or not p.get('documents'):gaps.append(p or seed)
        for d in p.get('documents',[]):
            m=d['model_raw']
            if seed['kind']=='jp_sitemap':
                m=heading_model(p['heading'],seed['url'])or d.get('model_raw','')
            is_software=software_source(seed['url'])
            if is_software:m=''  # A software version is not a hardware model.
            category='ソフトウェア（対応機種未確定）'if is_software else source_category(p)if seed['kind']=='jp_sitemap'else p['category']
            row=dict(maker='キヤノン',domain='家電',product_category=category,model_raw=m,
                model_normalized=unicodedata.normalize('NFKC',m).upper(),title=d['title'],url=d['url'],url_type=d['url_type'],source_method='sitemap'if seed['kind']=='jp_sitemap'else'crawl',
                first_seen='',http_status=d['http_status'],checked_at=d['checked_at'],model_unconfirmed='0'if m else'1',discontinued='1'if p['discontinued_explicit']else'')
            rows.append(row);evidence.append(dict(row,source_url=seed['url'],source_heading=p['heading'],discovery_url=seed['discovery_url'],
                model_assignment='explicit_Japan_region_selector'if seed['kind']=='ij_japan_selector'else d.get('model_assignment','product_specific_official_heading_or_unconfirmed'),
                section_heading=d.get('section_heading',''),
                model_mentioned_on_page=d.get('model_mentioned_on_page'),fetched_at=p['fetched_at']))
    rows=list({(r['model_raw'],r['url']):r for r in rows}.values())
    sample=random.Random(20261123).sample(rows,min(50,len(rows)));stats=Counter()
    statuses=check_urls(c,[r['url']for r in sample],stats,workers=3)
    for row in rows:
        if row['url']in statuses:row['http_status'],row['checked_at']=statuses[row['url']]
    write_rows(RAW/'canon_manuals.csv',rows);write_rows(RAW/'canon_head_sample.csv',sample)
    write_jsonl(RAW/'canon_evidence.jsonl',evidence);write_jsonl(RAW/'canon_gaps.jsonl',gaps)
    summary=dict(sitemap_source_pages=len(source_urls),ij_japan_selector_models=len(models),source_pages=len(sources),processed_pages=sum(p.get('status')==200 for p in pages.values()),
        failed_pages=sum(pages.get(x['url'],{}).get('status')!=200 for x in sources),source_pages_without_documents=len(gaps),rows=len(rows),
        named_models=len({r['model_raw']for r in rows if r['model_raw']}),unique_urls=len({r['url']for r in rows}),model_unconfirmed_rows=sum(r['model_unconfirmed']=='1'for r in rows),
        sample_rows=len(sample),sample_http=dict(Counter(r['http_status']for r in sample)),stats=dict(stats),age_cutoff=None,pdf_bodies_downloaded=0,
        scope='All pages discovered in JP manual sitemap plus all Japan-region IJ selector entries; not proof of all historical Canon products',completed_at=now())
    (RAW/'canon_build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');run()

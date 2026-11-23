"""Append one maker's sourced URL rows without rebuilding unrelated records.

Some historical additions exist only in manuals.csv, not raw/*_manuals.csv.
Re-running combine would lose them; preserve the existing bytes instead.
"""
import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from collector.common import ROOT, RAW, now

TARGETS = {
 '家電':['パナソニック','シャープ','ソニー','日立','東芝ライフスタイル','三菱電機','ダイキン','ゼネラル','象印','タイガー','アイリスオーヤマ','バルミューダ'],
 '通信':['ドコモ','au','ソフトバンク','楽天モバイル','Apple','Google','Samsung','バッファロー','NEC（Aterm）','アイ・オー・データ'],
 '車載':['パイオニア（carrozzeria）','ケンウッド','アルパイン','パナソニック（ストラーダ）','コムテック','ユピテル'],
 '住設':['リンナイ','ノーリツ','パロマ','TOTO','LIXIL','パナソニック ハウジング','タカラスタンダード','クリナップ','マックス']}

def append(key, maker):
    if not re.fullmatch('[a-z_]+',key):
        raise ValueError('Invalid maker key')
    main = ROOT/'output/manuals.csv'
    before = main.read_bytes()
    with main.open(encoding='utf-8',newline='') as f:
        reader = csv.DictReader(f);fields=reader.fieldnames;existing=list(reader)
    with (RAW/f'{key}_manuals.csv').open(encoding='utf-8',newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames!=fields:
            raise ValueError('CSV schema differs')
        rows=list(reader)
    if not rows or any(r['maker']!=maker for r in rows):
        raise ValueError('Empty or mixed-maker input')
    ident=lambda r:(r['maker'],r['model_raw'],r['url'])
    if len({ident(r)for r in rows})!=len(rows):
        raise ValueError('Duplicate model/URL input')
    old={ident(r)for r in existing}
    added=[r for r in rows if ident(r)not in old]
    if not added:
        print(json.dumps({'maker':maker,'added_rows':0,'already_present':len(rows)},ensure_ascii=False))
        return
    buf=io.StringIO(newline='')
    writer=csv.DictWriter(buf,fields,lineterminator='\r\n' if b'\r\n'in before else '\n')
    writer.writerows(added)
    if not before.endswith(b'\n'):
        raise ValueError('Existing CSV lacks final newline')
    main.write_bytes(before+buf.getvalue().encode('utf-8'))
    after=list(csv.DictReader(main.open(encoding='utf-8',newline='')))
    assert main.read_bytes().startswith(before) and after[:len(existing)]==existing
    receipt={'maker':maker,'added_rows':len(added),'original_rows':len(existing),'total_rows':len(after),
             'original_bytes_preserved':True,'original_sha256':hashlib.sha256(before).hexdigest(),
             'subaru_rows_preserved':sum(r['maker']=='スバル'for r in after),'at':now()}
    (RAW/f'{key}_append_validation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    counts=Counter(r['maker']for r in after)
    missing=[n for ns in TARGETS.values()for n in ns if not counts[n]]
    lines=['# 当初対象の収録状況','',f'更新: {now()}。台帳合計 {len(after):,} 行。',
           '',f'当初に個別名を挙げた37枠のうち、収録あり {37-len(missing)}、未収録 {len(missing)}。',
           '「収録あり」は1行以上あるという意味で、メーカー全機種の収集・本文検証完了を意味しない。',
           '', '| 分野 | メーカー・ブランド枠 | 台帳行数 | 状態 |','|---|---|---:|---|']
    for domain,names in TARGETS.items():
        for name in names:
            status='収録あり・範囲限定（各社notes参照）' if counts[name] else '未収録・取得経路の再調査対象'
            if counts[name] and name in ('Samsung','アイリスオーヤマ'):
                status='索引メタ情報のみ・配信未確認'
            if counts[name] and name=='タカラスタンダード':
                status='索引メタ情報6行＋HTML1行・範囲限定'
            lines.append(f'| {domain} | {name} | {counts[name]:,} | {status} |')
    named={n for ns in TARGETS.values()for n in ns}
    other=sorted(n for n in counts if n not in named)
    lines+=['','## その他の収録メーカー','', '指示書の「各自動車メーカー」に含まれる収録分。対象集合をこの一覧だけに限定しない。','']
    lines += [f'- {n}: {counts[n]:,}行'for n in other]
    lines+=['','PDF本体は保存しない。HTTP確認・型番と資料の対応・PDF本文照合は別の検証であり、各社notesに実施範囲を記す。','']
    (ROOT/'output/coverage.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('key');p.add_argument('maker');a=p.parse_args();append(a.key,a.maker)

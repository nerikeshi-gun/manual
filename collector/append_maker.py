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

# The original named targets are a starting list, not a ceiling. Keep missing
# manufacturers visible rather than dropping them from the denominator.
ADDITIONAL_TARGETS = {
 '家電':['キヤノン','エプソン','ブラザー','JVC／Victor','ヤマハ','ハイアール','アクア','ハイセンス','ツインバード','シロカ','山善','コロナ','トヨトミ'],
 '通信':['エレコム','TP-Link','ASUS'],
 '車載':['トヨタ','レクサス','日産','ホンダ','マツダ','三菱自動車','スズキ','ダイハツ','スバル','いすゞ','日野','三菱ふそう'],
 '住設':['長府製作所','KVK','SANEI','タカギ']}

def coverage(rows):
    counts=Counter(r['maker']for r in rows)
    all_targets={d:list(names)+ADDITIONAL_TARGETS.get(d,[])for d,names in TARGETS.items()}
    lines=['# メーカー・機種・資料の収集状況','',f'更新: {now()}。台帳合計 {len(rows):,} 行。',
        '', '対象は現行機種と過去機種。**当初の37枠は初期リストで、メーカー数の上限・全体の分母ではない。**',
        '下表はメーカー別の記録数であり、網羅率・完了率ではない。機種欄は型式文字列の種類数で、資料行数とは分ける。',
        '全機種・過去機種の網羅確認は未完了。公式掲載一覧を辿り終えた場合も、未掲載の歴史的全製品まで網羅したとは扱わない。',
        '', '| 分野 | メーカー・ブランド枠 | 型式文字列数 | 資料行数 | 状態 |','|---|---|---:|---:|---|']
    for domain,names in all_targets.items():
        for name in names:
            model_count=len({r['model_raw']for r in rows if r['maker']==name and r['model_raw']})
            status='部分収集・全機種／過去機種は未完了' if counts[name] else '未収集・取得経路調査対象'
            if counts[name] and name in ('Samsung','アイリスオーヤマ'):status='索引メタ情報のみ・配信未確認'
            if counts[name] and name=='タカラスタンダード':status='索引メタ情報＋HTML・範囲限定'
            if counts[name] and name in ('キヤノン','エプソン','ブラザー'):status='現行限定なしで公開一覧を巡回・残件は各社notes参照'
            lines.append(f'| {domain} | {name} | {model_count:,} | {counts[name]:,} | {status} |')
    named={n for names in all_targets.values()for n in names}
    other=sorted(n for n in counts if n not in named)
    if other:
        lines+=['','## その他の記録','']+[f'- {n}: {counts[n]:,}行'for n in other]
    lines+=['','追加調査リストも全メーカーを列挙したものではない。未収集メーカーと旧ブランドの棚卸しを継続する。',
        '旧ブランドのナショナル・三洋・富士通ゼネラル等も検索対象に含める。既存メーカーの1行だけで旧ブランド分まで収集済みとは扱わない。',
        'HTTP確認・公式掲載の型式対応・PDF本文照合は別の検証。PDF本文は保存せず、各社notesに実施範囲と取得不能・未掲載の範囲を残す。','']
    (ROOT/'output/coverage.md').write_text('\n'.join(lines),encoding='utf-8')

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
    coverage(after)
    print(json.dumps(receipt,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('key');p.add_argument('maker');a=p.parse_args();append(a.key,a.maker)

# 日産

ドメイン: 車載　／　コード: `collector/nissan.py`
生存確認の時期: 2026-11-14T02:45 〜 2026-11-14T03:14（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 18,977 |
| ユニークな取説URL | 1,643 |
| 型番（model_raw）の種類 | 540 |
| model_normalized の種類 | 68 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 18,967 |
| HTTP 404 | 10 |
| 不明（空欄） | 18,977 |
| URLの種類 html | 254 |
| URLの種類 pdf | 18,723 |

## 使った手段（収集コードの説明）

```
日産（www.nissan.co.jp/OPTIONAL-PARTS/NAVIOM/ 取扱説明書／点検整備方式）の車両取扱説明書URL収集。

ページはJS（JS/index2016.js）が index.xml（モデル一覧と年式）と XML/<モデルID>.xml（年式ごとの資料）を読んで表示する。
XML/<id>.xml: model > nenshiki(value=年式) > 資料区分 > [category(name)] > pdf(path, device) 。path はサイトルート相対。
資料区分のうち取説にあたるものを採る:
  op-inst=取扱説明書（デジタル） / guid=簡単早わかりガイド / tori=車両取扱説明書 /
  navi-maker=ナビゲーションシステム（標準・メーカーOP） / accessory=アクセサリー / navi-dealer=ナビ（ディーラーOP）
除外: movie（動画）, software（ソフトウェア更新）, im-sys（点検整備方式）。device は ALL と PC のみ（SP は同内容のスマホ版）。
model_raw は「モデル名／年式／資料の適用期間など」（指示書の車種/年式/グレード）。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": name_key(name), "title": title, "url": url
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 規約
- 「ご利用条件」を読んで同意した場合のみ利用、との表示（包括承認の範囲）。
## 範囲
- 動画、ソフトウェア更新、点検整備方式は取説ではないので除いた。
## 注意点
- 「ナビゲーションシステム（ディーラーオプション）」は、汎用のナビ取説（同じPDF）が各モデル・各年式に繰り返し載っている。
  サイトの表示どおり取り込んだため行数の大半（約1.6万行）を占める。車両の取説だけが欲しい場合は title の先頭で絞れる。

## 想定外の形のデータ（anomalies）

- shared_url: 1,379
- 一覧は `output/raw/nissan_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/nissan_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 49
- URLか資料名に型番あり: 1

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

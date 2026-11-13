# au

ドメイン: 通信　／　コード: `collector/au.py`
生存確認の時期: 2026-11-13T22:59 〜 2026-11-13T23:22（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 1,315 |
| ユニークな取説URL | 1,315 |
| 型番（model_raw）の種類 | 216 |
| model_normalized の種類 | 216 |
| 型番未確定（model_unconfirmed=1） | 74 |
| HTTP 200 | 1,315 |
| 不明（空欄） | 269 |
| 現行 | 1,046 |
| URLの種類 pdf | 1,315 |

## 使った手段（収集コードの説明）

```
au（www.au.com/support/service/mobile/manual/）の取説URL収集。

サイトマップには一覧ページしか載っていないため、取説コーナー配下（種別 → メーカー）だけを巡回する。
メーカー一覧ページに各機種のPDFが直接並んでおり、PDFのパス（/guide/manual/<機種>/pdf/）から機種を特定する。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": squash(model), "title": SIZE.sub("", l["label"]), "url": l["href"], "url_type": "pdf"
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 注意点
- 型番はPDFのパス（/manual/<型番>/pdf/）から取っている。パスに型番が無い行は `model_unconfirmed=1`。

## 想定外の形のデータ（anomalies）

- model_not_in_path: 74
- 一覧は `output/raw/au_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/au_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URLか資料名に型番あり: 43
- URL・資料名からは確認できず: 5
- URLか資料名に名称あり: 2

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

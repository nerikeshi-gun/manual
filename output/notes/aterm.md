# NEC（Aterm）

ドメイン: 通信　／　コード: `collector/aterm.py`
生存確認の時期: 2026-11-13T23:56 〜 2026-11-13T23:56（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 31 |
| ユニークな取説URL | 30 |
| 型番（model_raw）の種類 | 28 |
| model_normalized の種類 | 28 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 31 |
| 現行 | 31 |
| URLの種類 pdf | 31 |

## 使った手段（収集コードの説明）

```
NEC Aterm（www.aterm.jp/support/manual/）の取説URL収集。

マニュアルトップに並ぶ機種（/support/manual/<機種>/index.html）を現行品として扱い、各ページのPDFを拾う。
旧機種は別の一覧（/support/manual2/support/manual/）にあり、--phase rest で取る。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": squash(model), "title": l["label"], "url": l["href"], "url_type": "pdf"
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 範囲
- 現行品パスとして /support/manual/ に載る機種のみ。旧機種（/support/manual2/）は「さかのぼり」工程で取る予定。

## 想定外の形のデータ（anomalies）

- no_manual_links: 1
- shared_url: 1
- 一覧は `output/raw/aterm_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/aterm_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 31

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

# バルミューダ

ドメイン: 家電　／　コード: `collector/balmuda.py`
生存確認の時期: 2026-11-13T22:08 〜 2026-11-13T22:09（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 9 |
| ユニークな取説URL | 9 |
| 型番（model_raw）の種類 | 9 |
| model_normalized の種類 | 9 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 9 |
| 不明（空欄） | 8 |
| 生産終了・販売終了 | 1 |
| URLの種類 pdf | 9 |

## 使った手段（収集コードの説明）

```
バルミューダ（www.balmuda.com/jp/support/）の取説URL収集。

製品サポートページは十数件のみ。サポートトップの製品一覧（section-model）から各ページを開き、PDFリンクを拾う。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": model, "title": link["label"], "url": link["href"], "url_type": "pdf"
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 想定外の形のデータ（anomalies）

- no_manual_links: 10
- 一覧は `output/raw/balmuda_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/balmuda_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URLか資料名に型番あり: 8
- URL・資料名からは確認できず: 1

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

# ユピテル

ドメイン: 車載　／　コード: `collector/yupiteru.py`
生存確認の時期: 2026-11-14T00:15 〜 2026-11-14T00:20（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 445 |
| ユニークな取説URL | 279 |
| 型番（model_raw）の種類 | 254 |
| model_normalized の種類 | 254 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 445 |
| 現行 | 445 |
| URLの種類 pdf | 445 |

## 使った手段（収集コードの説明）

```
ユピテル（製品データベース www2.yupiteru.co.jp/manual/ → api.yupiteru.co.jp）の取説URL収集。

製品データベースは Vue アプリで、公開APIを呼んでいる（認証なし、robots.txt は制限なし）。
- 一覧: api/product_database/products?productReCategoryId=<id>&page=<n>（既定で販売終了品を除く。addEndSale=true で含む）
- 詳細: api/product_database/products/<id> の productDetails に取説PDFのリンク

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": squash(p["name"]), "title": d["title"], "url": d["linkUrl"]
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 範囲
- 製品データベースAPIは既定で販売終了品を除くため、現行品のみ。販売終了品は addEndSale=true で「さかのぼり」工程で取る予定。

## 想定外の形のデータ（anomalies）

- shared_url: 13
- no_manual_links: 2
- 一覧は `output/raw/yupiteru_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/yupiteru_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URLか資料名に型番あり: 31
- URL・資料名からは確認できず: 19

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

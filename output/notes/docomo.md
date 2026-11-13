# ドコモ

ドメイン: 通信　／　コード: `collector/docomo.py`
生存確認の時期: 2026-11-13T22:55 〜 2026-11-13T23:35（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 2,442 |
| ユニークな取説URL | 2,281 |
| 型番（model_raw）の種類 | 491 |
| model_normalized の種類 | 491 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 2,442 |
| 現行 | 2,442 |
| URLの種類 pdf | 2,442 |

## 使った手段（収集コードの説明）

```
ドコモ（www.docomo.ne.jp/support/manual/）の取説URL収集。


各機種ページの「ご利用条件」に同意（download.html へ a=manualDownloadLink をPOST）すると取説PDFの一覧が出る。
規約への同意はユーザーの承認済み（2026-11-13、同種の規約を含む）。同意はセッション単位なのでスレッドごとにセッションを分ける。
```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": squash(model_raw) if shown else p["ua"].upper(), "title": l["label"], "url": l["href"]
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 規約
- 取説ダウンロードは同意ボタン（download.html に a=manualDownloadLink を POST）が前提。包括承認により同意した。
## 注意点
- 現行品の判定が広めになっている（製品ページのカタログ走査で690機種を現行と判定）。

## 想定外の形のデータ（anomalies）

- page_not_200: 195
- shared_url: 35
- 一覧は `output/raw/docomo_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/docomo_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URLか資料名に型番あり: 43
- URL・資料名からは確認できず: 7

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

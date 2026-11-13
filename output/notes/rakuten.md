# 楽天モバイル

ドメイン: 通信　／　コード: `collector/rakuten.py`
生存確認の時期: 2026-11-13T22:36 〜 2026-11-13T22:36（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 17 |
| ユニークな取説URL | 17 |
| 型番（model_raw）の種類 | 11 |
| model_normalized の種類 | 11 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 17 |
| 現行 | 3 |
| 生産終了・販売終了 | 14 |
| URLの種類 pdf | 17 |

## 使った手段（収集コードの説明）

```
楽天モバイル（network.mobile.rakuten.co.jp）の端末取説URL収集。

サイトマップの製品ページ（/product/<種別>/<製品>/）を読み、PDFの取説リンクを拾う。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": re.sub(r"\s+", " ", p["title"]).upper()
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 注意点
- 製品ページ約600件のうち、取説PDFへのリンクがあるのは楽天モバイルブランドの端末（スマートフォンとWiFiルーター）のみ。他社製の端末はメーカーの取説を参照する形でリンクが無い。

## 想定外の形のデータ（anomalies）

- なし
- 一覧は `output/raw/rakuten_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/rakuten_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URLか資料名に型番あり: 17

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

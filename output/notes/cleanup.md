# クリナップ

ドメイン: 住設　／　コード: `collector/cleanup.py`
生存確認の時期: 2026-11-14T02:24 〜 2026-11-14T02:37（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 744 |
| ユニークな取説URL | 739 |
| 型番（model_raw）の種類 | 621 |
| model_normalized の種類 | 578 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 744 |
| 現行 | 391 |
| 生産終了・販売終了 | 353 |
| URLの種類 pdf | 744 |

## 使った手段（収集コードの説明）

```
クリナップ（cleanup.jp/support/manual/ 商品取扱説明書検索）の取説URL収集。

検索フォームは POST（sel01=種類 0:取扱説明書, sel02=商品カテゴリー, sel03=シリーズ 0:すべて, sel04/sel05=0, page=n）。
結果は ol.results の行（シリーズ・区分・品番・名称・発行年月・PDFリンク）、1ページ50件。
発行年月が「YYYY.MM - 現行」の行を現行品、「YYYY.MM - YYYY.MM」を販売終了品として扱う。
サイト注記: 2016年2月現行品以降が対象、一部検索に含まれない取説あり。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": squash(model), "title": title, "url": it["url"], "url_type": "pdf"
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 規約
- 取説検索に「当サービスのご利用条件」あり（包括承認の範囲）。
## 注意点
- サイトの注記どおり、2016年2月に現行だった商品以降が対象。一部検索に含まれない取説がある。

## 想定外の形のデータ（anomalies）

- shared_url: 1
- no_hinban: 1
- 一覧は `output/raw/cleanup_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/cleanup_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URLか資料名に型番あり: 43
- URLか資料名に名称あり: 6
- URL・資料名からは確認できず: 1

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

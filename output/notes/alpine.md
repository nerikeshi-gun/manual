# アルパイン

ドメイン: 車載　／　コード: `collector/alpine.py`
生存確認の時期: 2026-11-14T03:07 〜 2026-11-14T04:30（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 6,994 |
| ユニークな取説URL | 4,796 |
| 型番（model_raw）の種類 | 1,957 |
| model_normalized の種類 | 1,938 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 6,994 |
| 不明（空欄） | 6,994 |
| URLの種類 pdf | 6,994 |

## 使った手段（収集コードの説明）

```
アルパイン（products.alpine.co.jp/om/）の取説URL収集。

取説トップ（/om/owner/top）は「サーバが混雑しております」を返し続ける（2026-11-13, 11-14 とも）が、
検索 /om/owner/search?P0=<page>&P1=<キーワード> と製品別ページ /om/owner/product?P1=<id> は表示できる。
- 列挙: キーワード空の検索で全製品（発売の新しい順、10件/ページ）
- 販売終了: www.alpine.co.jp/archives（過去の製品一覧）に載る P1。phase current = 載らないもの、rest = 載るもの

製品ページは製品構成ごとに div.detailContents（h4 = 型番、表の th = 「資料名：ファイル名」、
リンク = owner/dl?P1=&P2=、application/octet-stream で PDF を返す）。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": squash(model), "title": (m.group(1) if m else l["label"]).strip()
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 注意点
- 取説トップ（/om/owner/top）は調査中ずっと「サーバが混雑しております」を返した。検索と製品別ページは使えたので、そちらから取った。
- 「過去の製品一覧」に載らない製品も、現行品とは限らないため `discontinued` は空欄（載るものは1）。

## 想定外の形のデータ（anomalies）

- no_manual_links: 19
- 一覧は `output/raw/alpine_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/alpine_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 50

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

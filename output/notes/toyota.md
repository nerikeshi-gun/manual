# トヨタ

ドメイン: 車載　／　コード: `collector/toyota.py`
生存確認の時期: 2026-11-14T02:37 〜 2026-11-14T03:00（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 1,332 |
| ユニークな取説URL | 1,313 |
| 型番（model_raw）の種類 | 1,237 |
| model_normalized の種類 | 109 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 1,330 |
| HTTP 403 | 2 |
| 現行 | 488 |
| 生産終了・販売終了 | 844 |
| URLの種類 html | 255 |
| URLの種類 pdf | 1,077 |

## 使った手段（収集コードの説明）

```
トヨタ（manual.toyota.jp）の車両取扱説明書URL収集。

車種一覧 manual.toyota.jp/index.html → 車種ページ manual.toyota.jp/<車種>/ 。
車種ページは世代（dl.block, dt h4 = 生産年月の範囲）ごとに、資料（div.manual, h5 = 資料名（グレード/動力））と
生産年月ごとのリンク（p = 「生産年月：…」, a = HTML/PDF）が並ぶ。
指示書の「車両は型番の代わりに 車種/年式/グレード」に沿い、model_raw を「車種／生産年月／グレード」とする。
生産年月が「…～」（終わりが無い）ものを現行（discontinued=0）、終わりがあるものを 1 とする。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": name_key(it["car"]), "title": it["doc"], "url": it["url"]
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 型番の扱い（車両）
- 指示書どおり型番の代わりに「車種／生産年月／グレード（動力）」を `model_raw` に入れた。`model_normalized` は車種名。
- 世代の生産年月が「…～」（終わり無し）なら現行（`discontinued=0`）。

## 想定外の形のデータ（anomalies）

- shared_url: 6
- 一覧は `output/raw/toyota_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/toyota_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 46
- URLか資料名に型番あり: 3
- URLか資料名に名称あり: 1

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

# レクサス

ドメイン: 車載　／　コード: `collector/lexus.py`
生存確認の時期: 2026-11-14T02:44 〜 2026-11-14T02:53（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 591 |
| ユニークな取説URL | 516 |
| 型番（model_raw）の種類 | 408 |
| model_normalized の種類 | 58 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 591 |
| 現行 | 189 |
| 生産終了・販売終了 | 402 |
| URLの種類 html | 108 |
| URLの種類 pdf | 483 |

## 使った手段（収集コードの説明）

```
レクサス（manual.lexus.jp）の車両取扱説明書URL収集。

車種一覧 manual.lexus.jp/ → 車種ページ manual.lexus.jp/<車種>/ 。
車種ページは div.mp-group（data-category = ガソリン/ハイブリッド等）ごとに、世代の .mp-unit（mp-unit_date = 生産年月、
mp-unit_model = モデル名）と、資料の .mp-unit（mp-unit_title）> li（mp-unit_listDate = 生産年月, a = HTML/PDF）が並ぶ。
model_raw は「モデル名／生産年月／動力（グレード相当）」。世代の生産年月が「…～」なら現行（discontinued=0）。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_raw": "／".join(x for x in (name, it["period"], it["power"]) if x), "model_normalized": name_key(name)
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 型番の扱い（車両）
- 「モデル名／生産年月／動力」を `model_raw` に入れた。`model_normalized` はモデル名。世代の生産年月が「…～」なら現行。

## 想定外の形のデータ（anomalies）

- shared_url: 64
- 一覧は `output/raw/lexus_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/lexus_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URLか資料名に型番あり: 35
- URL・資料名からは確認できず: 8
- URLか資料名に名称あり: 7

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

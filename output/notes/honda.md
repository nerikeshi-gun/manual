# ホンダ

ドメイン: 車載　／　コード: `collector/honda.py`
生存確認の時期: 2026-11-14T02:37 〜 2026-11-14T03:08（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 2,336 |
| ユニークな取説URL | 1,864 |
| 型番（model_raw）の種類 | 671 |
| model_normalized の種類 | 119 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 2,259 |
| HTTP 空欄（robots等で未確認） | 77 |
| 不明（空欄） | 2,336 |
| URLの種類 html | 180 |
| URLの種類 pdf | 2,156 |

## 使った手段（収集コードの説明）

```
ホンダ（四輪: www.honda.co.jp/ownersmanual/HondaMotor/auto/）の車両取扱説明書URL収集。

取扱説明書閲覧サービスはページ内JS（js/search.js）が data/search.json を読んで表示している（認証なし）。
search.json: CarModelData（車種）→ ModelYears（年式, ReleaseDate=発売年月）→ Docs（資料, DocCategoryId で資料名）。
URLの組み立ては search.js と同じ:
- PDF: <auto>/../../pdf/auto/<FolderName>/<PDFFileName>?<PDFParameter>（= /ownersmanual/pdf/auto/...）
- HTML（Web取説）: doc.WebOMFileName（そのまま）
- LINK: doc.LinkURL
指示書の「車両は型番の代わりに 車種/年式/グレード」に沿い、model_raw を「車種／年式（発売年月）」とする。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_raw": model, "model_normalized": name_key(car["Name"]), "title": title, "url": url
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 型番の扱い（車両）
- 「車種／年式（発売年月）」を `model_raw` に入れた。`model_normalized` は車種名。現行／生産終了の区別はデータに無いので `discontinued` は空欄。

## 想定外の形のデータ（anomalies）

- shared_url: 342
- 一覧は `output/raw/honda_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/honda_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 34
- URLか資料名に名称あり: 8
- URLか資料名に型番あり: 8

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

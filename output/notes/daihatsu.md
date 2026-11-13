# ダイハツ

ドメイン: 車載　／　コード: `collector/daihatsu.py`
生存確認の時期: 2026-11-14T02:46 〜 2026-11-14T02:46（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 42 |
| ユニークな取説URL | 42 |
| 型番（model_raw）の種類 | 22 |
| model_normalized の種類 | 15 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 42 |
| 不明（空欄） | 42 |
| URLの種類 pdf | 42 |

## 使った手段（収集コードの説明）

```
ダイハツ（www.daihatsu.co.jp/service/torisetu/）の車両取扱説明書URL収集。

車種一覧 service/torisetu/index.htm（と index2.htm）→ 車種のご利用条件 <車種>/index.htm（「同意する」は
<車種>/index_2.htm へ移るだけ。ユーザーの包括承認あり）→ <車種>/index_2.htm に PDF と説明（p.torisetu_text,
例「車両（詳細版）（2026年7月～）」）が並ぶ。
model_raw は「車種／適用期間」（指示書の車種/年式/グレード）。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_raw": "／".join(x for x in (car, period) if x), "model_normalized": name_key(car), "title": doc
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 規約
- 車種ごとに「ご利用条件」ページがあり、「同意する」は一覧ページ（index_2.htm）へ移るだけ（包括承認の範囲）。
## 範囲
- 掲載は現行車種の最新の取説のみ。

## 想定外の形のデータ（anomalies）

- なし
- 一覧は `output/raw/daihatsu_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/daihatsu_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 40
- URLか資料名に型番あり: 2

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

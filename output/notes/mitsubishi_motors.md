# 三菱自動車

ドメイン: 車載　／　コード: `collector/mitsubishi_motors.py`
生存確認の時期: 2026-11-14T02:42 〜 2026-11-14T02:43（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 92 |
| ユニークな取説URL | 57 |
| 型番（model_raw）の種類 | 40 |
| model_normalized の種類 | 18 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 92 |
| 不明（空欄） | 92 |
| URLの種類 html | 12 |
| URLの種類 pdf | 80 |

## 使った手段（収集コードの説明）

```
三菱自動車（www.mitsubishi-motors.co.jp/afterservice/manual/）の車両取扱説明書URL収集。

取扱説明書一覧ページ1枚に車種カード（li[data-carmodel]）があり、
「標準・メーカーオプション」「アクセサリー」（h3）ごとに PDF／HTML の取説リンクが並ぶ。
取扱説明動画・地図更新手順などのリンクは取説ではないので除く。
model_raw は「車種／版（YYYY年M月版）」（指示書の車種/年式/グレード。グレード相当の「PHEVモデル」等は title に残す）。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_raw": model, "model_normalized": name_key(car), "title": label
summary = {"rows": len(rows), "unique_urls": len(url_models), "cars": len({r["model_normalized"] for r in rows})
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 範囲
- 取扱説明書一覧ページ1枚（現行の車種18）。取扱説明動画・地図更新手順のリンクは除いた。

## 想定外の形のデータ（anomalies）

- shared_url: 17
- 一覧は `output/raw/mitsubishi_motors_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/mitsubishi_motors_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 49
- URLか資料名に名称あり: 1

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

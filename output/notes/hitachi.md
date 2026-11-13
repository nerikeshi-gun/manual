# 日立

ドメイン: 家電　／　コード: `collector/hitachi.py`
生存確認の時期: 2026-11-13T22:31 〜 2026-11-13T22:59（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 3,871 |
| ユニークな取説URL | 1,608 |
| 型番（model_raw）の種類 | 1,841 |
| model_normalized の種類 | 1,841 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 3,871 |
| 現行 | 3,871 |
| URLの種類 pdf | 3,871 |

## 使った手段（収集コードの説明）

```
日立（kadenfan.hitachi.co.jp）の取説URL収集。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_raw": p["model"], "model_normalized": normalize(p["model"]), "title": l["label"], "url": l["href"]
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 現行品の判定
- 取説一覧 search.json（全12,773件）のうち、日立の製品カタログページに型番が載るものを現行品とした。
## 取れなかった範囲
- 現行品以外は「さかのぼり」工程で取る予定。

## 想定外の形のデータ（anomalies）

- shared_url: 645
- no_manual_links: 45
- 一覧は `output/raw/hitachi_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/hitachi_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 31
- URLか資料名に型番あり: 19

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

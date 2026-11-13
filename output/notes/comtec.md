# コムテック

ドメイン: 車載　／　コード: `collector/comtec.py`
生存確認の時期: 2026-11-13T23:58 〜 2026-11-14T00:08（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 612 |
| ユニークな取説URL | 582 |
| 型番（model_raw）の種類 | 605 |
| model_normalized の種類 | 605 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 612 |
| 不明（空欄） | 612 |
| URLの種類 pdf | 612 |

## 使った手段（収集コードの説明）

```
コムテック（www.e-comtec.co.jp/0_etc/manual/）の取説URL収集。

取扱説明書ページ1枚に、製品カテゴリごとのプルダウン（option の value が PDF のパス、表示が型番）が並んでいる。
現行／生産終了の区別は無い。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": squash(model), "title": ("取扱説明書" + (f"（{edition.group(1)}）" if edition else ""))
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 注意点
- サイトに現行／生産終了の区別が無いため、全件を1回で取った。`discontinued` は空欄。

## 想定外の形のデータ（anomalies）

- shared_url: 23
- 一覧は `output/raw/comtec_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/comtec_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URLか資料名に型番あり: 37
- URL・資料名からは確認できず: 9
- URLか資料名に名称あり: 4

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

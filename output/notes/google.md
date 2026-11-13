# Google

ドメイン: 通信　／　コード: `collector/google.py`
生存確認の時期: 2026-11-14T02:33 〜 2026-11-14T02:33（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 41 |
| ユニークな取説URL | 35 |
| 型番（model_raw）の種類 | 41 |
| model_normalized の種類 | 41 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 41 |
| 不明（空欄） | 41 |
| URLの種類 html | 41 |

## 使った手段（収集コードの説明）

```
Google（Pixel）の取説相当ページの収集。

Google は機種別の取扱説明書PDFを出していない（使い方は Pixel ヘルプのWebページ）。
機種ごとに付属冊子に相当する「安全性と規制に関するガイド」がヘルプ記事として公開されているので、それを記録する。
入口: support.google.com/product-documentation/answer/9204905?hl=ja の
「安全と規制に関する情報」「アクセサリの安全と規制に関する情報」節のリンク（リンク文字列 = 機種名）。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": squash(re.sub(r"[（(]\d{4}[)）]", "", re.sub(r"^Google\s+", "", n))), "title": f"安全性と規制に関するガイド（{label}）"
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 注意点
- Google は機種別の取扱説明書PDFを出していない。付属冊子に相当する「安全性と規制に関するガイド」（ヘルプ記事）を機種ごとに記録した。
- support.google.com は存在するページにも HEAD で404を返す（GETは200）。HEAD が実質拒否されるため、Range 付き GET（先頭だけ）で確認した。

## 想定外の形のデータ（anomalies）

- なし
- 一覧は `output/raw/google_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/google_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URLか資料名に型番あり: 40
- URLか資料名に名称あり: 1

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

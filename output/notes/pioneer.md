# パイオニア

ドメイン: 車載　／　コード: `collector/pioneer.py`
生存確認の時期: 2026-11-14T01:00 〜 2026-11-14T02:41（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 5,782 |
| ユニークな取説URL | 5,770 |
| 型番（model_raw）の種類 | 2,034 |
| model_normalized の種類 | 2,028 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 5,782 |
| 不明（空欄） | 5,782 |
| URLの種類 pdf | 5,782 |

## 使った手段（収集コードの説明）

```
パイオニア（carrozzeria: jpn.pioneer/ja/support/）の取説URL収集。

カテゴリ（main_cd）→ サブカテゴリの発売順一覧（s-year.php, 新しい順）→ 機種（s-information.php）
→ 取扱説明書ページ（s-manual.php, 同じクエリ）の順に辿る。発売順に新しいものから取る。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": squash(model.split(" ")[0]), "title": SIZE.sub("", l["label"]) or l["row"][:60]
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 注意点
- 機種によっては取扱説明書のほか、バージョンアップ手順書・安全上のご注意・お客様登録申込書なども並ぶ。サイトの表示どおり取り込み、`title` で区別できる。
- 一部のページで PHP のソースコードがそのまま表示される不具合を見かけた（内容は使っていない）。

## 想定外の形のデータ（anomalies）

- no_manual_links: 1,021
- shared_url: 1
- 一覧は `output/raw/pioneer_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/pioneer_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 50

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

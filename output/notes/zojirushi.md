# 象印

ドメイン: 家電　／　コード: `collector/zojirushi.py`
生存確認の時期: 2026-11-13T22:14 〜 2026-11-13T22:24（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 848 |
| ユニークな取説URL | 554 |
| 型番（model_raw）の種類 | 759 |
| model_normalized の種類 | 759 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 848 |
| 現行 | 848 |
| URLの種類 pdf | 848 |

## 使った手段（収集コードの説明）

```
象印（www.zojirushi.co.jp/toiawase/manual/）の取説URL収集。

API・サイトマップが無いため、取説コーナー（/toiawase/manual/ 配下）だけを同一ドメイン内で巡回する。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_raw": model, "model_normalized": re.sub(r"\s+", "", model).upper()
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 注意点
- 生産終了の表示は商品カテゴリ単位の一覧にしかないため、`discontinued` はその一覧での表示に基づく。
- 1つの取説に複数型番が併記されている場合（例「NX-AB10/NX-AB18」）は型番ごとの行に分けた。

## 想定外の形のデータ（anomalies）

- shared_url: 197
- multi_model_page: 163
- no_manual_links: 86
- 一覧は `output/raw/zojirushi_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/zojirushi_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 48
- URLか資料名に型番あり: 2

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

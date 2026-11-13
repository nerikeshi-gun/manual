# ソニー

ドメイン: 家電　／　コード: `collector/sony.py`
生存確認の時期: 2026-11-13T22:10 〜 2026-11-13T22:12（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 1,197 |
| ユニークな取説URL | 547 |
| 型番（model_raw）の種類 | 376 |
| model_normalized の種類 | 376 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 274 |
| HTTP 空欄（robots等で未確認） | 923 |
| 現行 | 1,197 |
| URLの種類 html | 274 |
| URLの種類 pdf | 923 |

## 使った手段（収集コードの説明）

```
ソニー（support.sony.jp / www.sony.jp）の取説URL収集。


取説PDFは www.sony.com 上にあり、www.sony.com は robots.txt に403を返すため一切アクセスしない。
ヘルプガイド（helpguide.sony.net、HTML）は robots.txt が404のため生存確認を行う。
```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_raw": slug.upper(), "model_normalized": normalize(slug), "title": title, "url": url
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 現行品の判定
- ユーザーの指示「カタログで現行品を特定」により、www.sony.jp の各カテゴリのギャラリー（カタログ）に載る型番を現行品とした。
## 取れなかった範囲
- 取説PDFの多くは www.sony.com 上にあり、www.sony.com の robots.txt 自体が403を返すため一切アクセスしていない（`http_status` 空欄）。
- 現行品以外（サポートサイトのサイトマップにある約2.5万件のうち残り）は「さかのぼり」工程で取る予定。

## 想定外の形のデータ（anomalies）

- shared_url: 176
- page_not_200: 1
- 一覧は `output/raw/sony_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/sony_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 48
- URLか資料名に型番あり: 2

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

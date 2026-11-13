# LIXIL

ドメイン: 住設　／　コード: `collector/lixil.py`
生存確認の時期: 2026-11-14T00:22 〜 2026-11-14T00:31（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 498 |
| ユニークな取説URL | 498 |
| 型番（model_raw）の種類 | 492 |
| model_normalized の種類 | 492 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 498 |
| 不明（空欄） | 498 |
| URLの種類 html | 498 |

## 使った手段（収集コードの説明）

```
LIXIL（www.lixil.co.jp/support/manual/）のWeb取説（シリーズ単位）収集。

robots.txt の Sitemap にある web_manual_sitemap.xml（カテゴリ別）から各取説のトップ（/top?p_r_p_tag=）を読み、
タイトル（商品・シリーズ名）とURLを記録する。指示書「住設は品番のシリーズ単位でよい」に沿う。

品番単位の取説PDF（manualsearch?pid= → iinavi.inax.lixil.co.jp）は対象外:
- PDFのホスト iinavi.inax.lixil.co.jp は robots.txt で全面 Disallow。
- 品番ページは数十万件規模（1秒1回で約1週間）。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": re.sub(r"\s+", "", series), "title": p["manual"], "url": p["url"], "url_type": "html"
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 範囲
- 指示書の「住設は品番のシリーズ単位でよい」に沿い、Web取説（シリーズ単位）のみ。
- 品番単位の取説PDF（manualsearch → iinavi.inax.lixil.co.jp）は対象外：PDFのホストが robots.txt で全面禁止、品番ページは数十万件規模。扱いはユーザー判断待ち。

## 想定外の形のデータ（anomalies）

- なし
- 一覧は `output/raw/lixil_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/lixil_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URLか資料名に型番あり: 47
- URLか資料名に名称あり: 2
- URL・資料名からは確認できず: 1

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

# パナソニック ハウジング

ドメイン: 住設　／　コード: `collector/panasonic_housing.py`
生存確認の時期: - 〜 -（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 4,973 |
| ユニークな取説URL | 3,888 |
| 型番（model_raw）の種類 | 3,017 |
| model_normalized の種類 | 3,012 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 空欄（robots等で未確認） | 4,973 |
| 現行 | 3,668 |
| 生産終了・販売終了 | 1,305 |
| URLの種類 pdf | 4,973 |

## 使った手段（収集コードの説明）

```
パナソニック ハウジング（住宅設備・建材: www2.panasonic.biz Vカタ「図面・説明書 カテゴリ検索」）の取説URL収集。

入口: www2.panasonic.biz/jp/sumai/manual/（ご利用条件に同意の上で利用。条件は notice.html）
→ /scvb/a2A/zumenCategResult?CATEGORY_KAISO=/CTG005298/<分類>&CATEGORY_CD=...（GET, 公開ページ）
カテゴリは階層（goZumenCategoryKaiso のリンク）。「(N件)」の付く末端カテゴリで資料一覧が出る（20件/ページ、
listForm の START_CNT でページ送り）。各行: 名称・発売年月・品番（緑字）・「生産終了商品」表示・資料種別・PDF。
PDF は /ideacontout/... 上にあり robots.txt で Disallow のため、URLを記録するだけで生存確認はしない（http_status 空）。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": norm, "title": f"{it['doc']}（{it['name']}）"
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 規約
- 「ご利用条件」（/jp/sumai/manual/notice.html）に同意の上で利用（包括承認の範囲）。
## 取れなかった範囲
- 取説PDFの置き場所 /ideacontout/ は www2.panasonic.biz の robots.txt で Disallow のため、URLの記録のみで生存確認していない（`http_status` 空欄）。
- 単体ビルトイン機器・給湯機器（食洗機、IH、エコキュート、電気温水器、冷蔵庫）は別サイトのページで、まだ取っていない。
## 型番の扱い
- 一覧の緑字欄は品番のこともあれば発売年月や補足説明のこともある。品番らしい語だけのときは品番ごとの行、そうでなければ名称（＋補足）でシリーズ単位の1行にした（anomalies の series_level）。

## 想定外の形のデータ（anomalies）

- series_level: 2,876
- shared_url: 570
- 一覧は `output/raw/panasonic_housing_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/panasonic_housing_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 30
- URLか資料名に名称あり: 18
- URLか資料名に型番あり: 2

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

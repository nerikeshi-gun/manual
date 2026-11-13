# スズキ

ドメイン: 車載　／　コード: `collector/suzuki.py`
生存確認の時期: 2026-11-14T02:39 〜 2026-11-14T02:42（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 241 |
| ユニークな取説URL | 161 |
| 型番（model_raw）の種類 | 239 |
| model_normalized の種類 | 46 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 241 |
| 不明（空欄） | 241 |
| URLの種類 html | 1 |
| URLの種類 pdf | 240 |

## 使った手段（収集コードの説明）

```
スズキ（四輪: www.suzuki.co.jp/car/owners_manual/）の車両取扱説明書URL収集。

オーナーズマニュアルのページはJS（assets/js/common.js）が data/data.csv を読み、detail.js がリンクを組み立てる。
CSV列: 0 MAN_ID, 1 MAN_NO, 2 MAN_DT(適用年月 YYYYMM), 3 MAN_RF(抜粋版PDF名), 4 MAN_FL(PDF名), 5 MAN_HT(HTMLフォルダ),
 10 PRO_TP(Y=四輪), 11 CAR_SZ(1 軽/2 普通), 15 CAR_NM(車名), 16 MDL_CD(機種記号)
リンク（detail.js と同じ組み立て）:
- デジタル取扱説明書 HTML: /car/owners_manual/data/html/<MAN_HT>/ja/html/home.html?item=top.html
- 取扱説明書（抜粋版）PDF: ./data/pdf/<MAN_RF>.pdf
- 取扱説明書 PDF: ./data/pdf/<MAN_FL>.pdf
閲覧時はご利用条件（terms.html）への同意をブラウザの sessionStorage に記録するだけで、リンク自体は同意なしで開ける。
model_raw は「車名／機種記号／適用年月～」（指示書の車種/年式/グレード）。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"cars": len({r["model_normalized"] for r in rows}), "http": Counter(r["http_status"] for r in rows)
"model_raw": model, "model_normalized": name_key(r[15].strip()), "title": f"{title}（{r[1].strip()}）"
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 規約
- 閲覧時にご利用条件（terms.html）への同意をブラウザに記録するだけで、リンク自体は同意なしで開ける（包括承認の範囲）。
## 範囲
- data.csv に載るのは比較的新しい取説のみ（305件）。古いモデルの取説は掲載されていない。

## 想定外の形のデータ（anomalies）

- shared_url: 66
- 一覧は `output/raw/suzuki_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/suzuki_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 50

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

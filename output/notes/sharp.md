# シャープ

ドメイン: 家電　／　コード: `collector/sharp.py`
生存確認の時期: 2026-11-13T23:55 〜 2026-11-14T01:52（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 12,000 |
| ユニークな取説URL | 6,694 |
| 型番（model_raw）の種類 | 4,508 |
| model_normalized の種類 | 4,508 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 11,887 |
| HTTP 404 | 110 |
| HTTP 空欄（robots等で未確認） | 3 |
| 不明（空欄） | 12,000 |
| URLの種類 html | 614 |
| URLの種類 pdf | 11,386 |

## 使った手段（収集コードの説明）

```
シャープ（jp.sharp / cs.sharp.co.jp）の取説URL収集。


取説一覧（cs.sharp.co.jp/select/downloadInfo）は、利用規約ページ（select/download?productId=）で
「同意して次へ」を押した後に表示される。規約への同意はユーザーの承認済み（2026-11-13）。
同意と表示対象の型番はセッションに保持されるため、取得は1本の接続で順に行う。
```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_raw": model, "model_normalized": normalize(model), "title": title, "url": url
normalized_changed=sum(r["model_raw"] != r["model_normalized"] for r in rows))
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 規約
- 取説ダウンロード（cs.sharp.co.jp）は利用規約への同意が前提。ユーザーの指示「同意して進める」により同意して取得した。
## 注意点
- 1機種の資料欄に、取扱説明書のほか寸法図・工事説明書・仕様表なども並ぶ。サイトの表示どおり取り込み、`title` で区別できる。
- CADデータ（.dxf）は取説ではないので除いた。

## 想定外の形のデータ（anomalies）

- shared_url: 2,079
- non_document_file: 395
- no_manual_links: 12
- shown_model_differs: 4
- 一覧は `output/raw/sharp_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/sharp_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URLか資料名に型番あり: 31
- URL・資料名からは確認できず: 18
- URLか資料名に型番あり（HTTP 404）: 1

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

# 東芝ライフスタイル

ドメイン: 家電　／　コード: `collector/toshiba.py`
生存確認の時期: 2026-11-13T22:02 〜 2026-11-13T22:49（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 1,340 |
| ユニークな取説URL | 1,340 |
| 型番（model_raw）の種類 | 811 |
| model_normalized の種類 | 811 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 1,340 |
| 不明（空欄） | 1,340 |
| URLの種類 pdf | 1,340 |

## 使った手段（収集コードの説明）

```
東芝ライフスタイル（www.toshiba-living.jp）の取説URL収集。


取説一覧は「ご利用の条件」への同意（rev.php に YN=Y をPOST）の後に表示される。
規約への同意はユーザーの承認済み（2026-11-13、今後の同種の規約も含む）。
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

## 規約
- 取説の閲覧前に利用規約への同意（rev.php に YN=Y を送る）が要る。ユーザーの指示「今後も含め同意して進める」により同意した。
- 生存確認の HEAD は同意クッキーなしでも200を返した（URL単体で開ける）。
## 範囲
- 現行品パスとして、2024年1月以降に発売された機種のみ取得した。それ以前は「さかのぼり」工程で取る予定。

## 想定外の形のデータ（anomalies）

- shown_model_differs: 1
- 一覧は `output/raw/toshiba_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/toshiba_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 50

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

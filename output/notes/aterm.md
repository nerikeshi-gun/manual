# NEC（Aterm）

## 2026-11-23 全機種・過去機種の拡張

- 通常一覧 `/support/manual/` と**サポート終了品一覧 `/support/manual/index2.html`** を起点に、公開リンクを終端まで巡回。82ページ（一覧2、機種ページ76、旧共通ページ4）、取得失敗0。年式・現行限定・機種数の打切りなし。
- **旧メモの `/support/manual2/support/manual/index.html` は旧製品一覧ではなく正誤表だった。** このページを旧機種の分母にした処理は使用しない。新処理は `python -m collector.aterm_all`、既存CLIの `python -m collector.aterm run` も既定allとして新処理へ転送する。
- 556行、484 URL、非空の型式文字列156種類、型式未確定3行。既存31行との重複を除き525行を追加する。
- 旧共通ページのh3見出しと、その直後から次のh2/h3直前までの表を対応付ける。IT/ITX・IW・WL・WRなどの旧機器を含む。複数機種の共通見出しは原表記のまま保持し、全資料を個々の型式に推測で展開しない。周辺機器のガイドも公式の同一製品欄の掲載資料としてタイトルを保持する。
- 機種別ページはサイト共通h1を型式と誤認しないよう、文書title先頭の正式製品名を使用。正規化はNFKC・大文字化。機種番号のない共通機能資料は空欄・model_unconfirmed=1。既存台帳の値は変更しない。
- PDFに加え、公式に同じ機種から案内されるHTMLユーザーズマニュアル・機能詳細ガイドも収録。
- 無作為50行（シード20261123）のHEAD確認は全50行HTTP 200。PDF本文は取得しておらず、本文の型式一致率は未測定。仕様の本文50件照合は未実施。
- 資料URLを抽出できなかったページ1件を `aterm_all_gaps.jsonl` に保持。一覧終端までの巡回と、歴代全製品の網羅は別で、一覧から削除された製品・未公開資料の網羅は未確認。
- robots・1秒以上の間隔・連絡先入りUAを遵守。PDF本文は保存せず、HTTPのHEAD確認のみ。根拠は `aterm_all_pages.jsonl` / `aterm_all_evidence.jsonl`、件数は `aterm_all_build_summary.json`。

## 以下は2026-11-13時点の旧メモ

以下の31行・現行限定・旧入口の記述は過去の記録であり、上の拡張結果と訂正を優先する。

ドメイン: 通信　／　コード: `collector/aterm.py`
生存確認の時期: 2026-11-13T23:56 〜 2026-11-13T23:56（JST）

## 件数

| 項目 | 件数 |
|---|---|
| 行数（型番×取説URL） | 31 |
| ユニークな取説URL | 30 |
| 型番（model_raw）の種類 | 28 |
| model_normalized の種類 | 28 |
| 型番未確定（model_unconfirmed=1） | 0 |
| HTTP 200 | 31 |
| 現行 | 31 |
| URLの種類 pdf | 31 |

## 使った手段（収集コードの説明）

```
NEC Aterm（www.aterm.jp/support/manual/）の取説URL収集。

マニュアルトップに並ぶ機種（/support/manual/<機種>/index.html）を現行品として扱い、各ページのPDFを拾う。
旧機種は別の一覧（/support/manual2/support/manual/）にあり、--phase rest で取る。

```

## 共通事項

- `first_seen` は全行空欄（Common Crawl のインデックスサーバーに接続できなかったため。詳細は panasonic.md）。
- PDF本文はダウンロードしていない。生存確認は HEAD（拒否された場合のみ Range 付き GET で先頭だけ）。
- robots.txt で禁止されたURLにはアクセスせず、`http_status` を空欄にしている。

## 型番の正規化（model_normalized を作るコード）

```python
"model_normalized": squash(model), "title": l["label"], "url": l["href"], "url_type": "pdf"
```
`squash` = NFKC・大文字化のうえ英数字以外を除去。`name_key` = NFKC・大文字化のうえ空白と区切り記号（・：-／ 等）を除去し、日本語は残す。

## 範囲
- 現行品パスとして /support/manual/ に載る機種のみ。旧機種（/support/manual2/）は「さかのぼり」工程で取る予定。

## 想定外の形のデータ（anomalies）

- no_manual_links: 1
- shared_url: 1
- 一覧は `output/raw/aterm_anomalies.csv`。

## 検証（無作為50件、シード20261114）

抽出した行は `output/notes/aterm_verify_sample.csv`。PDF本文は取得しない方針のため、指示書の「PDFとの照合」は未実施（表の `pdf_model_by_hand` 列を空けてある）。代わりに、型番（車両・住設は名称）がURLか資料名に現れるかを機械的に確認した。

- URL・資料名からは確認できず: 31

「確認できず」は不一致を意味しない（ファイル名が通し番号のサイトでは常にこうなる）。

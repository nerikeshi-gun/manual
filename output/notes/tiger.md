# タイガー

2026-11-23の初回収集。現行商品一覧を起点とする部分収録。全機種・全取説の収集完了ではない。

## 結果

- 現行の日本向け商品一覧API13ページ、149商品を一巡。
- 取説リンクを得た商品75件。未取得74商品は raw/tiger_gaps.jsonl に残す。
- 型番×資料URL 118行、型番表記 116種類、資料URL 74件。
- 無作為50行（固定シード20261123、41URL）のHEAD確認はすべて200。
- 機種を特定できない資料はmodel_rawを空欄、model_unconfirmed=1とする。原文ラベルはevidenceに残す。
- 生産終了品専用の一覧は未列挙。PDF本文の無作為50件照合は未実施。

## 取得経路

- 公開商品一覧 https://www.tiger-corporation.com/ja/jpn/product/list/ のJSが呼ぶ、認証不要の `/wp-json/api/v1/product?region=jpn&detailed=true&paged=...` を使用。
- 検索APIの秘密値やログインは使用していない。API返却値の明示された商品URLを開く。
- 英語ページで資料が見つからない場合は、そのページ内の「日本語」リンクをたどる。
- 商品から明示的にリンクされたTIGER FORESTの公開取説ページの「日本語」PDFリンクを取得する。会員登録やログイン操作は行わない。
- 取説ページに具体的な型番一覧がある場合はその原表記を使用。シリーズ名しか無い場合は、同じ商品の公式名称に明示された具体的な型番を使い、補って推測しない。
- 例: JPV-Sの公開ページは https://www.tiger-forest.com/ja/manuals/rice-cooker/jpv-s 、PDFは末尾 `/file`。
- PDF本体はダウンロード・保存しない。robotsを確認し、同一ホストの送信間隔は1.05秒以上。
- 事前上限: 一覧200ページ、商品2,400件。実際の一覧は13ページで終端を確認。

## 未取得の扱い

- `search.tiger.jp/search` はrobotsで禁止されており、アクセスしない。
- 少なくともJRD-Aの商品ページでは、取説ボタンがこの検索URLのみを指していることを確認した。これを取説本文のURLとして収録しない。
- 未取得74商品のすべてを「資料なし」「取得不能」と断定しない。別の公開取説ページや公式索引の調査対象として残す。

## 証跡

raw/tiger_catalog.jsonl、tiger_pages.jsonl、tiger_evidence.jsonl、tiger_gaps.jsonl、tiger_manuals.csv、tiger_head_sample.csv、tiger_build_summary.json、tiger_append_validation.json。
HTTP確認と、公式の型番・資料リンクの対応確認と、PDF本文照合は別に扱う。

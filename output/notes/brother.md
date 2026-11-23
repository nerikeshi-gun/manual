# ブラザー

2026-11-23。公式製品マニュアル一覧を現行限定なしで巡回。

- 入口: https://support.brother.co.jp/j/b/productsearch.aspx?c=jp&lang=ja&content=ml 。21製品カテゴリーと、その製品系列・公開Ajax一覧を辿り、352一覧ページ・1,109機種ページを取得。取得失敗0。年式・モデル数の打切りなし。
- 結果: 1,106の型式文字列、7,365行、2,177 URL。系列ダイアログの「すべての製品を表示」内に初めから存在する旧製品リンクも含む。例えばDCP-110C等も対象。メーカーサイトから削除された歴代全製品を網羅したという意味ではない。
- 公開Ajaxは公式ページのスクリプトに記載される `productsearchajax.aspx?series=<実際の系列ID>&c=jp&lang=ja&pcatid=<掲載カテゴリーID>&content=ml`。IDは公式リンクから取得し、総当たりで推測しない。ログイン・トークン・CAPTCHAは不要。
- 一覧の `manualtop.aspx?...&prod=<掲載製品ID>` を取得し、`p.leadtxt` の正式型式を使用。例えば「DCP-C1xxxxx」という系列の案内ラベルを実機の型式として採用せず、実ページのDCP-C1210Nを使う。
- 各資料行の先頭セルにあるタイトルと、その同じ行のPDF／HTMLリンクを対応付ける。HTMLは `.../j/s/support/html/...` と `.../htmldoc/...` 等の公式配信を含む。カタログ・ライセンス文書は除外。
- 型式の原表記を保持し、正規化はNFKC・大文字化。全処理機種で型式表記がページ本文に存在することを確認した。生産終了は一般告知から推測せず空欄。表示名が複数製品の共通表記ならそのまま残し、色や派生型式は補完しない。
- 今回の解析で資料URLを抽出できなかった3機種を `brother_gaps.jsonl` に保持。「取説が存在しない」とは断定しない。
- 無作為50行（シード20261123）のHEAD確認は全50行HTTP 200。ただしPDF本文は取得しておらず、本文の型式一致率は未測定。仕様の本文50件照合は未実施。
- robots・1秒以上の間隔・連絡先入りUAを遵守。PDF本体は保存しない。会員領域・ダウンロード実行ファイルには入らない。
- 再現: `python -m collector.public_catalogs brother`。公開一覧・機種ページのチェックポイントから再開できる。根拠は `brother_listings.jsonl`, `brother_models.jsonl`, `brother_pages.jsonl`, `brother_evidence.jsonl`。件数は `brother_build_summary.json`。

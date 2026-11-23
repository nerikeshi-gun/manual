# アイリスオーヤマ

ドメイン: 家電

- 状態: **公式PDFの公開検索インデックスによる補足のみ**（2026-11-23）。ライブ取得・全機種収集は未完了。
- 件数: サーキュレーター4型式、6行・6 URL。PCF-SC15、PCF-SDS15T、PCF-HMK151、PCF-SDS15T-EC。
- 出典: `https://www.irisohyama.co.jp/products/manual/pdf/<ID>.pdf` の公開索引で明記されたメーカー名・型式・取説タイトル。PDF本文はダウンロードしていない。具体的な検索語と公式URLは `output/raw/iris_ohyama_index_seeds.json` に保持。
- `www.irisohyama.co.jp` はrobots取得403のため、PDFへのGET・HEADは実施していない。http_status / checked_at は空欄。公式索引上の対応は確認できるが、現在の配信と型式の一致・生存は未確認。
- CSVの既存source_methodは公式ページ由来の補足としてcrawlを使用。実際の発見は公式公開検索索引であり、ライブクロールでないことをevidenceの `discovery_method` / `direct_source_page_crawled` に記録した。
- 同一型式の別URLは別行。カラー記号を補完・展開せず、表紙メタ情報の型式をそのまま保持。正規化も原表記のまま。旧機種も足切りしない。
- 検証: 6行の索引にある型式対応のみ確認。PDF本文の型式一致率・生存は未測定。仕様のPDF本文50件検証は未実施。
- 未収集: 家電全分野の大部分、サーキュレーターのその他型式と各色型式、公式取説一覧のページ送り。販売店に他社製品もあるため、IRISブランドと確定できない通販PDFは今回採用しない。
- 再現: `python -m collector.index_manuals iris_ohyama`。シードの再ビルドであり索引の自動再検索ではない。

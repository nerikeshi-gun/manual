# Samsung

ドメイン: 通信

- 状態: **公式ページの公開検索インデックスによる補足のみ**（2026-11-23）。ライブ取得・全機種収集は未完了。
- 件数: Galaxy S25のSM-S931Q、3行・3 URL（Android 15 / 16 / 17の日本語マニュアル）。Safety Guideは今回含めない。
- 出典: https://www.samsung.com/jp/support/model/SM-S931QZRFSJP/ の公開検索インデックスに露出する `manuals[]` の `downloadUrl`、`description`、`languageList=JA`。ダウンロードURLのModelName=SM-S931Qも確認。SM-S938Qなどの共通マニュアルに含まれる他機種への対応は推測で追加しない。
- `www.samsung.com` はrobots取得403、実際の配信元 `org.downloadcenter.samsung.com` はrobots 200・Disallow: /。制限を回避した直接取得はせず、PDFのGET・HEADとも実施していない。http_status / checked_at は空欄。公開索引のメタ情報と現在の配信内容が一致するかは未確認。
- 既存CSVのsource_methodは列挙値を増やさず、公式ページ由来の補足としてcrawlを使用。ただし**直接クロールではない**。根拠JSONLに `discovery_method=official_public_search_index`, `direct_source_page_crawled=false`, `verification_method=official_index_metadata_only` を必ず保存して区別する。Kenwoodの公開索引補足と同様の手動シード方式。
- 型式はModelNameの原表記を保持し、正規化も同一。ファイル名のワイルドカード表記から型式を生成しない。
- PDF本文は保存・取得しておらず、本文の型式一致率と生存確認はいずれも未測定。3行の索引メタ情報対応のみ確認。仕様のPDF本文50件検証は未実施。
- 未収集: ほかのGalaxy型式、キャリア別型式、タブレット・ウェアラブル等すべて。ページ全体を巡回した結果ではないため、この3行でメーカー完了とはしない。
- 再現: `python -m collector.index_manuals samsung`。シードと根拠は `output/raw/samsung_index_seeds.json`, `samsung_evidence.jsonl`。シードの再ビルドであり公開索引の自動再検索ではない。

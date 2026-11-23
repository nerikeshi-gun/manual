# タカラスタンダード

ドメイン: 住設

- 状態: **公式PDFの公開検索索引6行＋公式FAQからのHTMLマニュアル1行**（2026-11-23）。全機種・生存確認・本文検証は未完了。
- 件数: 7行・5 URL、4型式／シリーズ。型式不明の共通お手入れ資料1行を含む。
- PDF: VUAシリーズ、VRAMシリーズは公式PDF公開索引の表紙にあるシリーズ名をそのまま保持。住設はシリーズ単位可の方針に従い、省略型番を補完・展開しない。浄水器TJS-SUI-HN-T / TJS-SUI-HN-TCは索引に明記されたセット品番で、取扱説明書と据付説明書それぞれの公開URLを保持。
- PDFホスト `www.takara-standard.co.jp` はrobots 403、`support.takara-standard.co.jp/faq/` はrobots禁止。これらのPDFへのGET・HEADは行わず、http_status / checked_at は空欄。索引メタ情報と現在の配信内容の一致は未確認。
- CSVのsource_methodは既存のcrawl。索引由来6行はevidenceで `official_public_search_index`、直接取得なし、配信未確認と明記。シードに公式URL・発見検索語を保持。ファイル名のみから型式を推定していない。
- HTML: https://qa.takara-standard.co.jp/fa/pblc/web/knowledge1708.html に実際にある「お手入れマニュアル」リンク `https://www.catalabo.org/cgi-bin/openCatalog.cgi?catalogId=0252_oteireMN` を辿り、公開ビューアのタイトル「タカラスタンダード株式会社 | 水まわりお手入れマニュアル」を確認。HTMLはHTTP 200。公式FAQが提供する外部配信資料で、特定の型式は表示されないため空欄・model_unconfirmed=1。
- 検証: 索引6行の型式／シリーズ対応と、HTML1行の公式リンク・発行元・タイトルを確認。PDF本体とビューア各ページの本文は取得・検証していないため型式一致率は未測定。仕様の本文50件検証は未実施。
- 未収集: キッチン、浴室、洗面、トイレ、給湯機の大部分と旧型式。今回の少数資料だけでメーカー完了とはしない。
- 再現: `python -m collector.takara_public`。索引分は保存シードの再ビルドであり自動再検索ではない。robots・1秒以上の間隔・連絡先入りUAを遵守し、会員ログインは使用しない。

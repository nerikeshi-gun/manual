# リンナイ

ドメイン: 住設

- 状態: **公開カタログ1系列を部分収集**（2026-11-23）。全製品完了ではない。
- 件数: 8型式、10行、4 URL。現行スタンダードガステーブルの公式ラインアップ掲載型式のみ。
- 入口: https://rinnai.jp/manual/ → 公開匿名サービス `https://rkids.rinnai.jp/rin/cgi-bin/xauth.cgi?str1=manual`。
- 型式出典: https://rinnai.jp/products/kitchen/gas_table/gt_metal/gt_metal_lineup 。ページに明記された8型式を保持し、左右・色の接尾辞も残す。正規化は原表記と同じ。
- 方法: 匿名セッション開始後、公開フォーム `itemSearch.cgi` に `item_search_type=<型式>,page=1,search_mode=type,header_type=manual` をPOST。検索表に同一型式がある行の `itemDetail.cgi?id=...` を開き、詳細の型式欄を完全一致確認して `imageDownload.cgi?id=...&age=orig&mode=2` を記録。
- ダウンロードURLは公開入口で開始した匿名セッションに依存する。新規セッションでURLだけ開くと認証エラーHTMLになる場合があり、安定した静的PDF URLではない。Cookieやセッション識別子は保存していない。会員ログイン・CAPTCHAは利用していない。
- 検証: 全10行の型式と公式詳細の対応を確認。HEADは全10行HTTP 200、`application/force-download...` の添付配信ヘッダー。PDF本文は取得しておらず、本文の型式一致率は未測定。50行未満のため今回の全10行を確認したが、仕様のPDF本文50件検証は未実施。
- 1つの取説が複数型式に共通。一部型式には取説に加えてクックブックも掲載されているため、別行として保持した。
- robots.txt・1秒以上の間隔・連絡先入りUAを遵守。旧メモの「ボット対策で未収集」は今回の公開経路では再現しなかった。
- 未収集: その他のガステーブル、ビルトインコンロ、給湯器など全領域、およびこのラインアップにない旧型式。
- 再現: `python -m collector.rinnai`。根拠は `output/raw/rinnai_evidence.jsonl`、件数は `rinnai_build_summary.json`。

# ダイキン

ドメイン: 家電

- 状態: **公開のリモコン・システム取説を部分収集**（2026-11-23）。全製品完了ではない。
- 件数: 13の型式・システム名、24行、19 URL。型式不明の別冊1行を含む。
- 出典: https://www.ac.daikin.co.jp/remocon_pa/manual と https://www.ac.daikin.co.jp/solution/dkconnect/document 。実在する取説リンクのみ。カタログ・仕様書は除外。
- 方法: リモコンはBRC1G1〜BRC1G5(K)の見出し直後のPDF、パネル・キットは表の型式欄と同じ行のPDFを対応付ける。rowspanの型式は次行の取付説明書にも適用。DK-CONNECTは公式のシステム名で9冊を記録。
- 正規化: 原文と同じ。括弧(K)は展開せず保持。DK-CONNECTはシステム単位。高暖房モード別冊は型式番号がないため空欄・model_unconfirmed=1。
- 内訳: リモコン5行、パネル・キット9行、高暖房モード別冊1行、DK-CONNECT9行。共有PDFは型式ごとに別行。
- 検証: 全24行の公式ページ対応を確認し、全19 URL（24行）がHEADでHTTP 200。PDF本文は取得しておらず、本文の型式一致率は未測定。仕様のPDF本文50件検証は未実施。
- robots.txt・1秒以上の間隔・連絡先入りUAを遵守。旧調査のfree.dtnetはrobots 403のため引き続き使わず、ページ内のログイン情報も利用しない。今回の別の公式公開ページでは固定PDFリンクを取得できた。
- 未収集: 家庭用エアコン、空気清浄機、給湯機ほか大部分の製品、今回未掲載の旧型式。
- 再現: `python -m collector.daikin_public`。根拠は `output/raw/daikin_public_evidence.jsonl`。

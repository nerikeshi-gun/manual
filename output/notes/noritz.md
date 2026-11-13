# ノーリツ（住設）

- 状態: **収集不可（robots.txt）**
- 件数: 0
- 取説の入口: www.noritz.co.jp/aftersupport/data/ の「取扱説明書検索」。検索は別サイト
  www.n-techdocs.com（製品データサービス, /search?...&manual=1）を開く方式。
- www.n-techdocs.com の robots.txt は `User-Agent: * / Disallow: /`（全面禁止）。
  取説の一覧・PDFはすべてこのサイト上にあるため収集しない。
- 手順上の誤り（2026-11-14）: 調査中に robots.txt の確認と同じコマンドで
  n-techdocs.com の検索ページ（キーワード空, manual=1）を1回 GET してしまった。
  取得内容（全65,749件・1,315ページという件数表示）はデータには使っていない。以後の調査は robots を確認するクライアント経由に統一した。
- 今後: 許可が得られれば再検討（このサイトは他社ブランド: ハーマン、リンナイ、パロマ等も含む）。

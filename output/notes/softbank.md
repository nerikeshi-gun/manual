# ソフトバンク

2026-11-23、直接開ける公式の機種別取説ページから初回収録。全端末の一覧収集は未完了。

## 結果

- 004Z、SoftBank 930CA、S5の3製品に対応する46行を取得。資料URLも46件。
- 4つの公式機種ページを調査し、あんしんファミリースマホのPDFページでは静的な資料リンクを取得できなかったため未取得として保持。
- 対象の46行すべてのHEADは200。PDF本文の型番照合は未実施。PDF本体は保存しない。

## 経路と以前の見送りの扱い

- 公式の公開検索結果で見つかった機種ページURLだけを初回の起点とした。起点はcollector/softbank_public.pyのSEEDSとraw/softbank_public_pages.jsonlに保持。
- 表示された機種名の見出しを原表記として保存し、その機種のディレクトリ内のPDFと、S5のオンラインマニュアル本体を対応づけた。共通フッターの約款・広告PDFは拾わない。
- 以前見送ったトークン付きの一覧・検索APIやブラウザによる検索操作は使っていない。今回確認した静的な公式機種ページを読む別経路。
- 年式で除外せず、公式に残っている旧機種のマニュアルも収録した。製品の現在の販売・サポート状況は推測しない。
- 正規化はNFKC・英字大文字化・空白除去のみ。原文のSoftBank表記や製品名を保持する。
- robotsを確認し、同一ホストの送信開始は1.05秒以上の間隔。

## 残り

他のスマートフォン・ケータイ・データ端末、端末一覧全体の列挙、今回リンクを取得できなかったPDFページは未完了。
raw/softbank_public_manuals.csv、softbank_public_pages.jsonl、softbank_public_evidence.jsonl、softbank_public_head_sample.csv、softbank_public_build_summary.json、softbank_public_append_validation.json に保存。

# バッファロー

2026-11-23、公開Wi-Fi商品カタログの代表型番から初回収録。全製品・全バリエーションの収集は未完了。

## 結果

- Wi-Fiルーター、Wi-Fi中継機、Wi-Fiアダプターの3カテゴリ、23代表型番。
- 型番×資料URL 135行、ユニーク資料URL95件。3カテゴリのAPI返却件数とtotalHitsは一致。
- 無作為50行の確認結果: 14行はHTTP 200、36行はrobotsによる未確認でHTTP欄を空欄とした。成功で埋めない。PDF本文照合は未実施。
- 取説APIに付随するFAQ参照リンク317件は取扱説明書として収録せず、buffalo_current_reference_links.jsonlに分けた。

## 経路

- 無線LANの公開カテゴリページがリンクする child_category/ap.html、extender.html、client.html を使用。
- ページに埋め込まれた .include-small-category-id の公開検索条件を、buffalo.jsと同じ product_search APIに渡して現行の表示対象を取得。
- APIが返す製品コード・型番の原表記をそのまま採用し、同じ型番の productDetail/manual のdownloadUrl・linkTextを資料へ対応づける。
- 認証用やprivate-IP許可用のAPIは使わず、private_groupのある資料は除く。今回は該当0件。
- PDFは保存しない。同一ホストの送信間隔は1.05秒以上、robotsを尊重する。公開APIからURLを取得できてもPDF配信先のrobotsでHEADできない場合がある。
- 新規の上限250型番。実際は23型番で、選択した3カテゴリの返却件数を一巡。

## 残りと証跡

HDD・SSD・NAS等の他カテゴリ、販売終了品、代表型番以外の全色・全容量などは未収集。
既存のbuffalo.pyは引き続き保存し、今回の取得コードはbuffalo_current.pyに分けた。
raw/buffalo_current_catalog.jsonl、buffalo_current_pages.jsonl、buffalo_current_evidence.jsonl、buffalo_current_gaps.jsonl、buffalo_current_reference_links.jsonl、buffalo_current_manuals.csv、buffalo_current_head_sample.csv、buffalo_current_build_summary.json、buffalo_current_append_validation.json に保存。

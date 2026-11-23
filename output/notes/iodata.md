# アイ・オー・データ

2026-11-23、公開サポートライブラリの更新掲載製品から初回収録。全製品カタログの収集は未完了。

## 結果

- https://www.iodata.jp/lib/ に明示された94製品を取得。
- 製品名×資料URL 238行、ユニーク資料URL46件。94製品すべてで資料リンクを取得し、APIの製品IDと取得元IDの一致も確認。
- 無作為50行（固定シード20261123）のHEAD確認はすべて200。共有資料のため、異なる型番が同じURLを参照する場合がある。
- 未確認のHTTP状態は空欄。PDF本文の無作為50件照合は未実施。PDF本体は保存しない。

## 経路と旧記録の訂正

- 公開の product.js が呼ぶ、認証不要の /lib/script/product.php?code=<ライブラリID> を使用。
- 製品IDは公開HTMLにある /lib/product/<頭文字>/<ID>.htm のリンクから得る。IDの連番推測はしない。
- APIの product.name と product.man の File_Name・Title、および同じ資料欄の明示リンクを対応づける。
- /man/ はrobotsで禁止されているが、今回の /lib/manual/ は別の公開パスであり、同じものとして扱わない。旧「/man/禁止のため未収集」をメーカー全体へ広げていた記録を訂正する。
- ブラウザへの秘密情報の埋め込み、ログイン、会員操作は使っていない。同一ホスト1.05秒以上の間隔、User-Agentに連絡先を含める。
- 事前の範囲は /lib/ 更新一覧のリンク先、上限300製品。初回94製品を収録した。

## 残りと証跡

更新一覧に載らない製品、過去の製品、全カテゴリ・全型番の列挙は未実施。
raw/iodata_models.jsonl、iodata_pages.jsonl、iodata_evidence.jsonl、iodata_gaps.jsonl、iodata_manuals.csv、iodata_head_sample.csv、iodata_build_summary.json、iodata_append_validation.json に保存。

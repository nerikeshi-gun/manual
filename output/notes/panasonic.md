# パナソニック（panasonic.jp）

収集期間：2026-11-10 23:16 〜 2026-11-12 12:33（JST）
対象：panasonic.jp の家電サポート。ストラーダ（car.panasonic.jp）と パナソニック ハウジング（www2.panasonic.biz）は指示書上の別メーカー枠のため対象外。

## 件数

| 項目 | 件数 |
|---|---|
| 取説ありとしてAPIが返した型番 | 20,628 |
| サポートページを取得できた型番 | 20,477 |
| `manuals.csv` の行数（型番×取説URL） | 25,559 |
| ユニークな取説URL | 14,685 |
| 生産終了表示のある型番 | 17,856 |
| `product_category` が空欄の型番 | 4,058（5,083行） |
| `title` が空欄の行（リンク表記が型番だけ） | 2,328 |
| 正規化で色記号を除いた行 | 332 |

リクエスト総数は27,454件（GET 27,442、HEAD 12）。内訳はローカルの `output/logs/panasonic_requests.log` に1件1行で記録してある（gitには含めない）。

## 使った手段

### 1. Common Crawl CDX：使えず
- `https://index.commoncrawl.org/collinfo.json` へのTCP接続が、11/10と11/12の計6回すべてタイムアウトした。DNSは解決でき、`commoncrawl.org` 本体には接続できたので、障害はインデックスサーバー側にある。
- このため `first_seen` は全行空欄。

### 2. サポートサイトの検索API：型番の列挙に使用
- 取説検索ページ `https://panasonic.jp/support/products.html?category_uid=<uid>&narrowing_down=userManual` をPlaywright（ヘッドレス）で開き、XHRを記録して特定した。
- エンドポイント：`GET https://1006091-adobeiopisc.adobeioruntime.net/api/v1/web/PanasonicCIF-2.0.0/io`
  - GraphQLで、パラメータは `query`、`variables`、`operationName=SiteSearch`。認証やAPIキーは不要。このホストの robots.txt は404。
  - 取説ありの絞り込み：`filter={"is_plan":false,"is_instructions":true,"type":"5"}`。カテゴリで絞る場合は `category_uid` を加える。
  - 戻り値 `supports[]`：`sku`、`name`、`release_date`、`status_icons`（「生産終了」）、`url`（`/c-sites/product.html?hb=<SKU>&tab=support`）。
  - 1回の取得件数 `limit` は、100ならエラーにならず、500だと400エラーが返る。`offset` は20,600でも結果が返る。
- `manuals` フィールドは常に空で、このAPIからは取説URLが返らない。
- 列挙の流れ：
  1. `/support/manual.html` のカテゴリリンク729本を、それぞれ100件ずつページングして集めた。結果は16,419型番。
  2. API全体の総数20,628との差が出たため、絞り込みなしでも全件を読み、4,209型番を追加した。この4,209型番は、どのカテゴリにも属さないので `product_category` が空欄になる。
  3. 最終的に20,628型番がそろい、API全体の総数と一致した。

### 3. サイトマップ：使えず
- robots.txt に Sitemap 行がない。
- `/sitemap.xml` は存在するが、URLは195件だけで、`amp`、`bj2020`、`tokyo2020`、`tourist` の特設ページしか入っていない。製品ページもサポートページも含まれない。

### 4. サポートページの取得：取説URLの取得に使用
- 型番ごとにサポートページ `https://panasonic.jp/<カテゴリパス>/products/<SKU>/support.html` を取得し、`id="manual"` の要素の中にあるリンクを取説として抽出した。
  - APIが返す `c-sites/product.html?hb=…` は、このページへ301でリダイレクトされる。
  - カテゴリパスはカテゴリごとに一度学習し、2件目からはリダイレクトを省いた。
  - 型番に `/` を含むもの（例：`BK-4HCC/4`）は、ページのURLでは `_` に置き換わる（`BK-4HCC_4`）。
- これは同一ドメイン内を広く巡回するクロールではなく、APIで列挙した型番のページだけを取りに行ったもの。ただ、URLはHTMLから読み取っているので `source_method=crawl` とした。
- 取説PDFのURL構造：`/content/dam/panasonic/jp/ja/pim-assets/support/manual/<3桁区切りのID>/<ID15桁>/<ファイル名>.pdf`
  - ファイル名は、型番そのまま、シリーズ名、`p_<型番>_t_<日時>_0.pdf` などが混在している。

## 取れなかった範囲

| 範囲 | 件数 | 理由 |
|---|---|---|
| パソコン（CF-xxx） | 108型番 | サポートページが別サイト `jp-pc-support.connect.panasonic.com` へ301リダイレクトされる。同一ドメインの原則に従い、追跡していない。 |
| カーナビ（CN-xxx） | 43型番 | `panasonic.jp/car/products/<SKU>/support.html` が404。ストラーダは指示書上の別メーカー枠。 |
| 取説の生存確認（`http_status`） | 全25,559行 | 下記「robots.txt」の項を参照。 |
| `first_seen` | 全行 | CDXに接続できなかったため。 |

### robots.txt による制約（重要）
`panasonic.jp/robots.txt` は、次の1行で取説PDFの置き場所そのものを禁止している。

```
Disallow: /content/dam/panasonic/jp/ja/pim-assets/support/manual/*.pdf$
```

- そのため、HEADでの生存確認も、PDF本文との型番照合も行っていない。`http_status` と `checked_at` は空欄。実施するにはパナソニックの許可が必要。
- **規則に反したアクセス12件**：拡張子が大文字の `.PDF` のURL12件について、CSV作成工程（11/12）でHEADを送ってしまった。12件ともステータスは200。
  - robots.txt の照合は大文字小文字を区別するため、規則の文面上は対象外と判定された。しかし、規則の趣旨には反する。
  - 対応として、大文字小文字にかかわらず不可と扱うよう修正済み。CSVの該当行も空欄に戻した。
- `www.panasonic.com` と `ec-plus.panasonic.jp`（ストア）は robots.txt 自体が403を返すため、一切アクセスしていない。取説の収集には不要。

## 型番の扱い
- `model_raw`：APIの `sku` をそのまま入れた。リンク表記中の型番（括弧内）は `output/raw/panasonic_pages.jsonl` に原文のまま残してある。
- `model_normalized`：Unicode正規化（NFKC）、空白除去、大文字化に加え、末尾の色記号を除く。
  - 対象の色記号：`-W -K -H -N -C -S -T -R -A -P -G -B -D -V -CK -HK -PK -WK`
  - 実績：-K 91、-S 71、-W 49、-CK 39、-A 23、-R 12、-H 11、-N 9、-T 8、-C 7、-P 7、-B 5。
  - `-A` や `-S` は色以外の意味を持つ可能性もあるが、元の表記は `model_raw` に残している。
- 年度記号は除かない（例：`NA-FW10K2` の `K2`）。年度が違えば取説も別のため。
- `/` を含む型番（`CS-256SB/S` など）は、そのまま残す。
- 全行で型番が確定しているため、`model_unconfirmed` は全行0。
- `discontinued`：APIの `status_icons` に「生産終了」があれば1。
- 発売日はCSVの列にはなく、`output/raw/panasonic_models.jsonl` の `release_date` に入っている。ただし513件はダミーの1900/01/01、66件は空欄。

## 想定外の形のデータ
一覧は `output/raw/panasonic_anomalies.csv` にある。

| 種類 | 件数 | 例 |
|---|---|---|
| 1つのURLを複数の型番で共用 | 4,175 URL（15,049行） | 最大は107型番で、`viera_channel_guide.pdf` を共用 |
| 複数の型番を併記したリンク表記 | 7,051 | `NR-SJD5102、JD5102V`、`NA-F10AKE1,_NA-9AKE1_NA-8AKE1`（省略表記） |
| シリーズ名だけの表記 | 3,062 | `15年度EXシリーズ`、`13Fシリーズ(2.2kW～4.0kW)`（エアコンに多い） |
| 表記の型番がページの型番と違う | 549 | セット品で、構成品の取説が付いているもの（`K-KJ23MCC02` → `BQ-CC23`）など |
| 取説以外の文書も「取扱説明書」欄にある | — | アプリのスタートガイド、チャンネル一覧表、交換用紙パック一覧、「ソフトウェアについて」など。サイトの表示どおり取り込んでいる。 |
| リンク表記が型番だけ | 2,328行 | `SDR-S7`。推測で埋めず、`title` を空欄にした。 |
| リンク表記の書式が古い | — | `SQ-LD100-K(取扱説明書)`。括弧内をタイトルとして扱った。 |

## 検証（50件の無作為抽出、シードは固定）
抽出した50件は `output/notes/panasonic_verify_sample.csv` にある。

- PDF本文との照合は、robots.txt の制約により未実施。そのため、指示書の定義どおりの不一致率はまだ出せない。
  - サンプル表の `pdf_model_by_hand` 列を空けてあるので、許可が出たら手で埋められる。
- 代わりに、PDFを開かずにできる範囲で照合した。結果は次の通り。
  - サイト上のリンク表記かファイル名で型番が一致したもの：23/50（46%）。
  - 一致を確認できなかったもの：27/50（54%）。内訳は下表の通り。
  - 明らかに別の製品の取説に見えるものは0件だった。

| 一致を確認できなかったパターン | 件数 | 例 |
|---|---|---|
| シリーズ名だけの表記やファイル名 | 15 | `CS-280DAX` → `[20AXシリーズ]` / `cs_20ax.pdf` |
| 省略形での複数機種併記 | 6 | `EP-MS41` → `EP-MS50/41` |
| 色や仕様違いの派生型番 | 2 | `NA-LX129EL` → `NA-LX129E` |
| セット品の構成品の取説 | 2 | `N-TGN01-6ASET` → `NC-TGN01.pdf` |
| ファイル名が同じシリーズの別型番 | 2 | `KZ-HS60B` → `KZ-HS75B.pdf` |

## 変更候補（提案のみ。未実施）
1. 取説PDFへのHEADアクセスと本文照合について、パナソニックの許可を取る。
2. `first_seen` の代わりに、APIの `release_date`（発売日）をCSVの列に加える。発売年での足切りの判断材料になる。
3. CDXの代替として、`data.commoncrawl.org` の cc-index ファイル（cluster.idx と各シャード）を直接引く。ただし、指示書の手段から外れる。
4. `title` で取説以外の文書（アプリ利用規約やチャンネル一覧など）を除外するかどうかを決める。
5. パソコン（`jp-pc-support.connect.panasonic.com`）を別の取得先として扱うかどうかを決める。
6. 1社あたりの取得時間：サーバーの応答が1件あたり約3〜6秒と遅く、今回は約37時間かかった。1秒1回の上限内で同時接続を2〜3本にすれば短縮できる。
